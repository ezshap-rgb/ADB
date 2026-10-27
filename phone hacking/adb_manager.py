from __future__ import annotations

import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional


ROOT = Path(__file__).resolve().parent
ADB = ROOT / "platform-tools" / "adb.exe"

# Curated Bloatware Intelligence Database
# Maps package names to: (Friendly Name, Category, Safety Level, Description)
# Safety levels: "Safe", "Caution", "Essential"
BLOATWARE_DATABASE: dict[str, tuple[str, str, str, str]] = {
    # Facebook / Meta
    "com.facebook.katana": ("Facebook", "Social", "Safe", "Main Facebook app. Safe to remove if unused."),
    "com.facebook.orca": ("Messenger", "Social", "Safe", "Facebook Messenger app."),
    "com.facebook.system": ("Meta App Installer", "Telemetry", "Safe", "Background installer for Facebook updates and analytics."),
    "com.facebook.appmanager": ("Meta App Manager", "Telemetry", "Safe", "Background manager for Meta apps; consumes RAM and telemetry."),
    "com.facebook.services": ("Meta Services", "Telemetry", "Safe", "Meta telemetry service. High recommendation to disable."),
    
    # Microsoft
    "com.microsoft.skydrive": ("OneDrive", "Microsoft", "Safe", "Microsoft cloud storage. Safe to remove if unused."),
    "com.microsoft.office.officehubrow": ("Microsoft 365 (Office)", "Microsoft", "Safe", "Microsoft Office suite pre-install."),
    "com.microsoft.office.outlook": ("Outlook", "Microsoft", "Safe", "Microsoft Outlook email app."),
    "com.linkedin.android": ("LinkedIn", "Social", "Safe", "LinkedIn pre-installed app."),
    
    # Google Services & Bloat
    "com.google.android.youtube": ("YouTube", "Google", "Safe", "YouTube video streaming."),
    "com.google.android.apps.tachyon": ("Google Meet (Duo)", "Google", "Safe", "Google video calling."),
    "com.google.android.music": ("Google Play Music", "Google", "Safe", "Discontinued music app; safe to remove."),
    "com.google.android.videos": ("Google TV", "Google", "Safe", "Google Movies and TV streaming."),
    "com.google.android.apps.photos": ("Google Photos", "Google", "Safe", "Cloud photo backup and gallery."),
    "com.google.android.apps.docs": ("Google Drive", "Google", "Safe", "Google Drive cloud client."),
    "com.google.android.apps.podcasts": ("Google Podcasts", "Google", "Safe", "Discontinued Google Podcasts app."),
    "com.google.android.feedback": ("Market Feedback Agent", "Telemetry", "Safe", "Diagnostic feedback sender for Google Play."),
    "com.google.android.apps.wellbeing": ("Digital Wellbeing", "Google", "Caution", "Usage tracking. Safe to remove, but disables screen-time tracking."),
    "com.google.android.googlequicksearchbox": ("Google Search / Assistant", "Google", "Caution", "Google search bar and Google Assistant."),
    "com.google.android.chrome": ("Google Chrome", "Google", "Safe", "Chrome browser. Safe to remove if you use another browser."),
    "com.google.android.gm": ("Gmail", "Google", "Safe", "Google email client."),
    "com.google.android.apps.maps": ("Google Maps", "Google", "Safe", "Google Maps and navigation."),
    "com.google.android.gms": ("Google Play Services", "Core", "Essential", "CRITICAL. Required for push notifications and Play Store."),
    "com.android.vending": ("Google Play Store", "Google", "Caution", "Official app store. Can be locked/hidden or restored for child-safe phone management."),
    "com.google.android.vending": ("Google Play Store", "Google", "Caution", "Official app store. Can be locked/hidden or restored for child-safe phone management."),
    "com.google.android.gsf": ("Google Services Framework", "Core", "Essential", "CRITICAL. Core framework for Google cloud services."),

    # Samsung Bloatware
    "com.samsung.android.bixby.agent": ("Bixby Voice", "Samsung", "Safe", "Samsung voice assistant. Safe to disable if unused."),
    "com.samsung.android.bixby.service": ("Bixby Service", "Samsung", "Safe", "Bixby background service."),
    "com.samsung.android.app.spage": ("Samsung Free / Daily", "Samsung", "Safe", "News feed left of home screen. Common bloatware."),
    "com.samsung.android.game.gamehome": ("Gaming Hub (Game Launcher)", "Samsung", "Safe", "Samsung game launcher and ads."),
    "com.samsung.android.game.gametools": ("Game Booster", "Samsung", "Safe", "In-game overlay and optimization."),
    "com.samsung.android.game.gos": ("Game Optimizing Service (GOS)", "Samsung", "Safe", "Throttles games and apps to conserve battery."),
    "com.sec.android.app.samsungapps": ("Galaxy Store", "Samsung", "Caution", "Samsung app store. Needed for Samsung system app updates."),
    "com.samsung.android.spay": ("Samsung Wallet / Pay", "Samsung", "Caution", "Samsung Pay app. Remove only if not using Samsung Pay."),
    "com.samsung.android.app.tips": ("Samsung Tips", "Samsung", "Safe", "Introductory tips popups."),
    "com.samsung.android.kidsinstaller": ("Samsung Kids Installer", "Samsung", "Safe", "Stub for Samsung Kids mode."),
    "com.samsung.android.arzone": ("AR Zone", "Samsung", "Safe", "Augmented reality camera features."),
    "com.samsung.android.aremoji": ("AR Emoji", "Samsung", "Safe", "Samsung 3D avatar emojis."),

    # Xiaomi / MIUI Bloatware
    "com.miui.analytics": ("MIUI Analytics", "Xiaomi", "Safe", "MIUI telemetry and usage tracking. Recommended to remove."),
    "com.miui.msa.global": ("MIUI System Ads (MSA)", "Xiaomi", "Safe", "Xiaomi system advertising daemon. Safe and recommended to remove."),
    "com.miui.bugreport": ("MIUI Bug Report", "Xiaomi", "Safe", "Telemetry report sender."),
    "com.mi.globalbrowser": ("Mi Browser", "Xiaomi", "Safe", "Default Xiaomi browser. Contains telemetry and ads."),
    "com.miui.videoplayer": ("Mi Video", "Xiaomi", "Safe", "Default Xiaomi video player with ads."),
    "com.miui.player": ("Mi Music", "Xiaomi", "Safe", "Xiaomi music player with online service ads."),
    "com.miui.yellowpage": ("Yellow Pages", "Xiaomi", "Safe", "Caller ID and Chinese directories."),
    "com.xiaomi.joyose": ("Joyose", "Xiaomi", "Safe", "Telemetry and throttling daemon. Safe to remove."),

    # Carrier & Commercial Bloat
    "com.amazon.mShop.android.shopping": ("Amazon Shopping", "OEM", "Safe", "Pre-installed Amazon store app."),
    "com.amazon.appmanager": ("Amazon App Manager", "OEM", "Safe", "Amazon background manager."),
    "com.netflix.partner.activation": ("Netflix Activation", "OEM", "Safe", "Pre-loaded Netflix activation partner."),
    "com.netflix.mediaclient": ("Netflix", "OEM", "Safe", "Netflix streaming app."),
    "com.spotify.music": ("Spotify", "OEM", "Safe", "Pre-installed Spotify music client."),
    "com.vzw.hss.myverizon": ("My Verizon", "Carrier", "Safe", "Verizon carrier account manager."),
    "com.att.myWireless": ("myAT&T", "Carrier", "Safe", "AT&T carrier account manager."),
    "com.tmobile.pr.mytmobile": ("T-Mobile", "Carrier", "Safe", "T-Mobile account app."),
    "com.sprint.ms.smf.services": ("Sprint Services", "Carrier", "Safe", "Sprint carrier bloatware services."),
}

# Critical prefixes that the curated UI will strictly protect
PROTECTED_PREFIXES = (
    "android",
    "com.android.settings",
    "com.android.systemui",
    "com.google.android.permissioncontroller",
    "com.google.android.packageinstaller",
    "com.android.phone",
    "com.android.providers.telephony",
)


@dataclass
class PackageItem:
    package: str
    name: str
    is_system: bool
    status: str       # "Enabled", "Disabled", "Uninstalled (User 0)"
    safety: str       # "Safe", "Caution", "Essential", "Unknown"
    category: str     # "Google", "Samsung", "Xiaomi", "Carrier", "Social", "OEM", "General"
    description: str


@dataclass
class AdbResult:
    code: int
    stdout: str
    stderr: str


class AdbClient:
    def __init__(self, executable: Path = ADB):
        self.executable = executable

    def available(self) -> bool:
        return self.executable.is_file()

    def run(self, args: list[str], timeout: int = 30) -> AdbResult:
        if not self.available():
            return AdbResult(-1, "", f"ADB was not found at: {self.executable}")
        try:
            completed = subprocess.run(
                [str(self.executable), *args],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
            )
            return AdbResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())
        except subprocess.TimeoutExpired:
            return AdbResult(-1, "", f"ADB command timed out after {timeout} seconds")
        except OSError as exc:
            return AdbResult(-1, "", str(exc))

    def devices(self) -> AdbResult:
        return self.run(["devices", "-l"])

    def shell(self, serial: str, *args: str, timeout: int = 30) -> AdbResult:
        return self.run(["-s", serial, "shell", *args], timeout)

    def package_list_full(self, serial: str) -> dict[str, PackageItem]:
        """
        Queries Android package manager for accurate enabled/disabled/uninstalled states
        and classifies each package with safety intelligence.
        """
        # Read various package sets
        all_pkg_res = self.shell(serial, "pm", "list", "packages", "-a")
        uninstalled_res = self.shell(serial, "pm", "list", "packages", "-u")
        system_res = self.shell(serial, "pm", "list", "packages", "-s")
        disabled_res = self.shell(serial, "pm", "list", "packages", "-d")
        enabled_res = self.shell(serial, "pm", "list", "packages", "-e")

        def parse(res: AdbResult) -> set[str]:
            if res.code != 0:
                return set()
            return {
                line.removeprefix("package:").strip()
                for line in res.stdout.splitlines()
                if line.startswith("package:")
            }

        all_pkgs = parse(all_pkg_res)
        uninstalled_pkgs = parse(uninstalled_res)
        system_pkgs = parse(system_res)
        disabled_pkgs = parse(disabled_res)
        enabled_pkgs = parse(enabled_res)

        # Union of all known packages (including uninstalled for user 0)
        combined_names = sorted(all_pkgs | uninstalled_pkgs, key=str.casefold)
        result: dict[str, PackageItem] = {}

        for pkg in combined_names:
            is_sys = pkg in system_pkgs
            
            # Accurate status
            if pkg in disabled_pkgs:
                status = "Disabled"
            elif pkg not in all_pkgs and pkg in uninstalled_pkgs:
                status = "Uninstalled (User 0)"
            elif pkg in enabled_pkgs or pkg in all_pkgs:
                status = "Enabled"
            else:
                status = "Unknown"

            # Intelligence lookup or heuristic classification
            if pkg in BLOATWARE_DATABASE:
                name, cat, safety, desc = BLOATWARE_DATABASE[pkg]
            else:
                name = self._heuristic_name(pkg)
                cat, safety, desc = self._heuristic_bloat_check(pkg)

            # Override core protection
            if pkg.startswith(PROTECTED_PREFIXES):
                safety = "Essential"
                desc = "Core Android system framework component. Do not remove."

            result[pkg] = PackageItem(
                package=pkg,
                name=name,
                is_system=is_sys,
                status=status,
                safety=safety,
                category=cat,
                description=desc,
            )

        return result

    @staticmethod
    def _heuristic_name(package: str) -> str:
        last = package.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ")
        return last.title() if last and last != package else package

    @staticmethod
    def _heuristic_bloat_check(package: str) -> tuple[str, str, str]:
        pkg = package.lower()
        if "facebook" in pkg or "meta" in pkg:
            return "Social", "Safe", "Facebook/Meta service or app."
        if any(c in pkg for c in ("vzw", "verizon", "att", "tmobile", "sprint", "vodafone", "telecom")):
            return "Carrier", "Safe", "Likely carrier-specific application or bloatware."
        if "analytics" in pkg or "telemetry" in pkg or "tracking" in pkg or "diagnostics" in pkg:
            return "Telemetry", "Safe", "Vendor telemetry or analytics collection package."
        if "samsung" in pkg or "sec.android" in pkg:
            return "Samsung", "Caution", "Samsung OEM application or background service."
        if "miui" in pkg or "xiaomi" in pkg:
            return "Xiaomi", "Caution", "Xiaomi/MIUI OEM application or background service."
        if "amazon" in pkg:
            return "Amazon", "Safe", "Amazon pre-installed shopping or media app."
        return "General", "Unknown", "Installed Android package."


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ADB Device Manager & Bloatware Controller")
        self.geometry("1060x720")
        self.minsize(860, 560)
        self.client = AdbClient()
        self.selected_serial = ""
        self.packages_data: dict[str, PackageItem] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self._last_detected_devices: list[str] = []

        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._process_events)
        self.after(300, self.refresh_devices)
        self.after(3000, self._auto_poll_devices)

    def _on_close(self) -> None:
        """Cleanly releases the USB connection on app exit so WebUSB isn't blocked."""
        try:
            self.client.run(["kill-server"], timeout=3)
        except Exception:
            pass
        self.destroy()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("SubTitle.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Muted.TLabel", foreground="#666666")
        style.configure("Danger.TButton", foreground="#9b1c1c")
        style.configure("Success.TLabel", foreground="#15803d", font=("Segoe UI", 9, "bold"))
        style.configure("Warning.TLabel", foreground="#b45309", font=("Segoe UI", 9, "bold"))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(18, 12, 18, 6))
        header.pack(fill="x")
        ttk.Label(header, text="ADB Device Manager & Debloater", style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="Starting…")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        # Device connection bar
        device_bar = ttk.LabelFrame(self, text="Device Connection", padding=8)
        device_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_bar, textvariable=self.device_var, state="readonly", width=50)
        self.device_combo.pack(side="left", padx=(0, 8))
        self.device_combo.bind("<<ComboboxSelected>>", self._device_changed)
        ttk.Button(device_bar, text="Refresh", command=self.refresh_devices).pack(side="left")
        
        self.device_info_var = tk.StringVar(value="No device selected")
        ttk.Label(device_bar, textvariable=self.device_info_var, style="Muted.TLabel").pack(side="left", padx=14)

        # Main tabs
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self.guide_tab = ttk.Frame(self.tabs, padding=14)
        self.apps_tab = ttk.Frame(self.tabs, padding=10)
        self.tools_tab = ttk.Frame(self.tabs, padding=12)
        self.console_tab = ttk.Frame(self.tabs, padding=10)
        self.reference_tab = ttk.Frame(self.tabs, padding=10)

        self.tabs.add(self.guide_tab, text="Getting Started")
        self.tabs.add(self.apps_tab, text="Apps & Debloat")
        self.tabs.add(self.tools_tab, text="Tools & Diagnostics")
        self.tabs.add(self.console_tab, text="Advanced Console")
        self.tabs.add(self.reference_tab, text="Command Reference")

        self._build_guide_tab()
        self._build_apps_tab()
        self._build_tools_tab()
        self._build_console_tab()
        self._build_reference_tab()

    def _auto_poll_devices(self) -> None:
        """Lightweight background check for USB hotplug detection without freezing UI."""
        if not self.busy:
            def worker():
                res = self.client.devices()
                if res.code == 0:
                    current = [l.strip() for l in res.stdout.splitlines()[1:] if l.strip()]
                    if current != self._last_detected_devices:
                        self.events.put(("hotplug_changed", res))
            threading.Thread(target=worker, daemon=True).start()
        self.after(3000, self._auto_poll_devices)

    def _build_guide_tab(self) -> None:
        ttk.Label(self.guide_tab, text="Connect your Android phone", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.guide_tab, text="Follow these steps each time you use the program. The device will be detected automatically.", style="Muted.TLabel").pack(anchor="w", pady=(4, 14))
        self.guide_status_var = tk.StringVar(value="Step 1 of 5")
        ttk.Label(self.guide_tab, textvariable=self.guide_status_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.guide_text = tk.Text(self.guide_tab, height=10, width=80, wrap="word", relief="flat", background=self.cget("background"))
        self.guide_text.pack(fill="x", pady=8)
        self.guide_text.configure(state="disabled")
        buttons = ttk.Frame(self.guide_tab)
        buttons.pack(fill="x")
        self.guide_back = ttk.Button(buttons, text="Back", command=lambda: self._guide_move(-1))
        self.guide_back.pack(side="left")
        self.guide_next = ttk.Button(buttons, text="Next", command=lambda: self._guide_move(1))
        self.guide_next.pack(side="left", padx=8)
        ttk.Button(buttons, text="Check connection", command=self.refresh_devices).pack(side="left")
        ttk.Button(buttons, text="Open Apps Tab", command=lambda: self.tabs.select(self.apps_tab)).pack(side="right")
        self.guide_step = 0
        self._update_guide()

    def _guide_move(self, delta: int) -> None:
        self.guide_step = max(0, min(4, self.guide_step + delta))
        self._update_guide()

    def _update_guide(self) -> None:
        steps = [
            ("Prepare the phone", "Keep the phone unlocked and use a working USB data cable. Charge the phone if you will be making several changes."),
            ("Enable Developer options", "On the phone, open Settings > About phone. Tap Build number seven times until it says you are a developer."),
            ("Enable USB debugging", "Open Settings > System > Developer options, then turn on USB debugging."),
            ("Connect and authorize", "Connect the phone to this computer via USB. Unlock the phone and choose Allow on the USB debugging prompt."),
            ("Load apps & debloat", "Once the device appears above, click 'Load installed apps'. You can filter by 'Safe Bloatware' and disable or uninstall with full safeguards."),
        ]
        title, body = steps[self.guide_step]
        self.guide_status_var.set(f"Step {self.guide_step + 1} of {len(steps)}: {title}")
        self.guide_text.configure(state="normal")
        self.guide_text.delete("1.0", "end")
        self.guide_text.insert("1.0", body)
        self.guide_text.configure(state="disabled")
        self.guide_back.configure(state="normal" if self.guide_step else "disabled")
        self.guide_next.configure(text="Finish" if self.guide_step == len(steps) - 1 else "Next")

    def _build_apps_tab(self) -> None:
        # Child-Safe Mode Banner for Google Play Store
        parental_bar = ttk.LabelFrame(self.apps_tab, text="Child-Safe Mode: Google Play Store (com.android.vending)", padding=(8, 4))
        parental_bar.pack(fill="x", pady=(0, 6))
        self.play_store_status_var = tk.StringVar(value="Play Store Status: Connect device & load apps")
        ttk.Label(parental_bar, textvariable=self.play_store_status_var, font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
        self.play_store_btn_var = tk.StringVar(value="🛡️ Lock / Restore Play Store")
        ttk.Button(parental_bar, textvariable=self.play_store_btn_var, command=self.toggle_play_store).pack(side="right", padx=6)

        # Search and filter controls
        top = ttk.Frame(self.apps_tab)
        top.pack(fill="x", pady=(0, 8))

        ttk.Label(top, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_packages())
        ttk.Entry(top, textvariable=self.search_var, width=24).pack(side="left", padx=(6, 12))

        ttk.Label(top, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar(value="All Packages")
        filter_combo = ttk.Combobox(
            top,
            textvariable=self.filter_var,
            state="readonly",
            width=22,
            values=(
                "All Packages",
                "Safe Bloatware",
                "Caution / Optional",
                "Carrier Bloat",
                "OEM (Samsung/Xiaomi)",
                "Telemetry & Ads",
                "Disabled / Uninstalled",
            ),
        )
        filter_combo.pack(side="left", padx=(6, 12))
        filter_combo.bind("<<ComboboxSelected>>", lambda _: self._filter_packages())

        ttk.Button(top, text="Load installed apps", command=self.load_packages).pack(side="left")
        ttk.Button(top, text="Select Safe Bloatware", command=self.select_recommended_bloat).pack(side="left", padx=6)
        ttk.Button(top, text="Export list", command=self.export_packages).pack(side="left")
        ttk.Button(top, text="Import list", command=self.import_packages).pack(side="left", padx=6)

        # Center area: Package Tree + Action Panel
        app_content = ttk.Frame(self.apps_tab)
        app_content.pack(fill="both", expand=True)

        self.app_tabs = ttk.Notebook(app_content)
        self.app_tabs.pack(side="left", fill="both", expand=True)

        self.all_apps_tab = ttk.Frame(self.app_tabs, padding=(0, 4, 0, 0))
        self.system_apps_tab = ttk.Frame(self.app_tabs, padding=(0, 4, 0, 0))
        self.user_apps_tab = ttk.Frame(self.app_tabs, padding=(0, 4, 0, 0))

        self.app_tabs.add(self.all_apps_tab, text="All apps (0)")
        self.app_tabs.add(self.system_apps_tab, text="System apps (0)")
        self.app_tabs.add(self.user_apps_tab, text="User apps (0)")

        self.all_tree = self._create_package_tree(self.all_apps_tab)
        self.system_tree = self._create_package_tree(self.system_apps_tab)
        self.user_tree = self._create_package_tree(self.user_apps_tab)
        self.package_tree = self.all_tree

        self.app_tabs.bind("<<NotebookTabChanged>>", self._app_tab_changed)

        # Right Action Panel
        actions = ttk.LabelFrame(app_content, text="Debloat Actions", padding=8)
        actions.pack(side="right", fill="y", padx=(10, 0), pady=(4, 0))

        ttk.Button(actions, text="Disable selected", command=lambda: self.change_selected("disable"), width=22).pack(fill="x", pady=3)
        ttk.Button(actions, text="Enable selected", command=lambda: self.change_selected("enable"), width=22).pack(fill="x", pady=3)
        ttk.Button(actions, text="Uninstall (User 0)", style="Danger.TButton", command=self.uninstall_selected, width=22).pack(fill="x", pady=3)
        ttk.Button(actions, text="Restore selected", command=self.restore_selected, width=22).pack(fill="x", pady=3)

        ttk.Separator(actions, orient="horizontal").pack(fill="x", pady=8)

        # Quick single-app control buttons
        ttk.Label(actions, text="Quick App Control:", style="SubTitle.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Button(actions, text="Force Stop", command=self.force_stop_selected, width=22).pack(fill="x", pady=2)
        ttk.Button(actions, text="Clear App Cache/Data", command=self.clear_data_selected, width=22).pack(fill="x", pady=2)

        ttk.Separator(actions, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(
            actions,
            text="Tip: Prefer 'Disable' over 'Uninstall' because disabled apps can be re-enabled instantly with zero data loss.",
            style="Muted.TLabel",
            wraplength=165,
        ).pack(fill="x")

        # Bottom Inspector Drawer
        self.inspector = ttk.LabelFrame(self.apps_tab, text="Package Inspector", padding=8)
        self.inspector.pack(fill="x", pady=(8, 0))
        self.inspector_label = tk.StringVar(value="Select an application above to inspect its safety rating, APK path, and description.")
        ttk.Label(self.inspector, textvariable=self.inspector_label, wraplength=950).pack(anchor="w")

    def _create_package_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        content = ttk.Frame(parent)
        content.pack(fill="both", expand=True)
        columns = ("name", "safety", "status", "category", "package")
        tree = ttk.Treeview(content, columns=columns, show="headings", selectmode="extended")
        tree.heading("name", text="App Name")
        tree.heading("safety", text="Safety")
        tree.heading("status", text="Status")
        tree.heading("category", text="Category")
        tree.heading("package", text="Package ID")

        tree.column("name", width=190, anchor="w")
        tree.column("safety", width=85, anchor="center")
        tree.column("status", width=120, anchor="center")
        tree.column("category", width=95, anchor="center")
        tree.column("package", width=340, anchor="w")

        scroll = ttk.Scrollbar(content, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        return tree

    def _app_tab_changed(self, _event: object = None) -> None:
        idx = self.app_tabs.index("current")
        if idx == 0:
            self.package_tree = self.all_tree
        elif idx == 1:
            self.package_tree = self.system_tree
        else:
            self.package_tree = self.user_tree

    def _on_tree_select(self, _event: object = None) -> None:
        selected = self.package_tree.selection()
        if not selected:
            return
        pkg = self.package_tree.item(selected[0], "values")[4]
        item = self.packages_data.get(pkg)
        if item:
            safety_badge = f"[{item.safety.upper()}]"
            self.inspector_label.set(
                f"{item.name} ({item.package})\n"
                f"Safety: {safety_badge}  |  Category: {item.category}  |  Status: {item.status}  |  Type: {'System' if item.is_system else 'User'}\n"
                f"Description: {item.description}"
            )

    def _build_tools_tab(self) -> None:
        # Child-Safe Mode: Google Play Store Control
        play_box = ttk.LabelFrame(self.tools_tab, text="Child-Safe Mode: Google Play Store (com.android.vending)", padding=12)
        play_box.pack(fill="x", anchor="n", pady=(0, 10))
        ttk.Label(
            play_box,
            text="Easily lock or restore Google Play Store on a child's phone. Restoring reinstalls directly from the phone's internal system partition with ZERO APK download required.",
            wraplength=850,
        ).pack(anchor="w")
        p_row = ttk.Frame(play_box)
        p_row.pack(fill="x", pady=(8, 0))
        ttk.Button(p_row, text="🛡️ Lock Phone (Hide & Uninstall Play Store)", command=self.lock_play_store).pack(side="left", padx=(0, 8))
        ttk.Button(p_row, text="🔓 Unlock Phone (Restore & Enable Play Store)", command=self.restore_play_store).pack(side="left", padx=8)

        # Device Power & Reboot controls
        reboot_box = ttk.LabelFrame(self.tools_tab, text="Device Power & Recovery Controls", padding=12)
        reboot_box.pack(fill="x", anchor="n")
        reboot_row = ttk.Frame(reboot_box)
        reboot_row.pack(fill="x")
        ttk.Button(reboot_row, text="Restart Phone (Normal)", command=lambda: self.run_reboot("")).pack(side="left", padx=(0, 8))
        ttk.Button(reboot_row, text="Reboot to Recovery", command=lambda: self.run_reboot("recovery")).pack(side="left", padx=8)
        ttk.Button(reboot_row, text="Reboot to Bootloader / Fastboot", command=lambda: self.run_reboot("bootloader")).pack(side="left", padx=8)

        # APK installation
        box = ttk.LabelFrame(self.tools_tab, text="APK Installation", padding=12)
        box.pack(fill="x", anchor="n", pady=10)
        ttk.Label(box, text="Sideload and install an APK file on the selected device directly via ADB.").pack(anchor="w")
        ttk.Button(box, text="Choose APK and Install", command=self.install_apk).pack(anchor="w", pady=(8, 0))

        # Backup & Export
        backup = ttk.LabelFrame(self.tools_tab, text="Backup & Presets", padding=12)
        backup.pack(fill="x", anchor="n")
        ttk.Label(backup, text="Save the list of installed or disabled apps to a JSON preset file to restore or review later.").pack(anchor="w")
        ttk.Button(backup, text="Export Current App List", command=self.export_packages).pack(anchor="w", pady=(8, 0))

        # Log view
        self.tools_log = tk.Text(self.tools_tab, height=12, state="disabled", wrap="word")
        self.tools_log.pack(fill="both", expand=True, pady=(10, 0))

    def _build_console_tab(self) -> None:
        ttk.Label(
            self.console_tab,
            text="Advanced ADB Shell mode. Type commands such as: pm list packages, or dumpsys battery",
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w")
        row = ttk.Frame(self.console_tab)
        row.pack(fill="x", pady=8)
        self.console_mode_var = tk.StringVar(value="Phone shell command")
        ttk.Combobox(
            row,
            textvariable=self.console_mode_var,
            state="readonly",
            width=24,
            values=("Phone shell command", "ADB command arguments"),
        ).pack(side="left", padx=(0, 8))
        self.console_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.console_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _: self.run_console())
        ttk.Button(row, text="Run command", command=self.run_console).pack(side="left", padx=(8, 0))
        self.console_output = tk.Text(self.console_tab, state="disabled", wrap="word")
        self.console_output.pack(fill="both", expand=True)

    def _build_reference_tab(self) -> None:
        ttk.Label(self.reference_tab, text="ADB and Android Shell Command Reference", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.reference_tab,
            text="Common ADB commands for package control and debugging.",
            style="Muted.TLabel",
            wraplength=850,
        ).pack(anchor="w", pady=(4, 10))
        columns = ("command", "purpose")
        tree = ttk.Treeview(self.reference_tab, columns=columns, show="headings")
        tree.heading("command", text="Command")
        tree.heading("purpose", text="What it does")
        tree.column("command", width=420, anchor="w")
        tree.column("purpose", width=510, anchor="w")
        entries = [
            ("adb devices -l", "List connected devices and USB authorization state."),
            ("adb shell pm disable-user --user 0 PKG", "Safely disable package for primary user (non-root safe)."),
            ("adb shell pm enable PKG", "Re-enable a previously disabled package."),
            ("adb shell pm uninstall --user 0 PKG", "Remove package for user 0 while keeping OEM system APK."),
            ("adb shell cmd package install-existing PKG", "Restore a package uninstalled for user 0."),
            ("adb shell am force-stop PKG", "Kill running background processes for the given app."),
            ("adb shell pm clear PKG", "Reset app data and cache back to initial install state."),
            ("adb shell pm list packages -d", "List all currently disabled packages on device."),
            ("adb shell pm list packages -u", "List packages including uninstalled system packages."),
            ("adb shell pm path PKG", "Show the physical APK filesystem path for a package."),
            ("adb reboot", "Restart the phone normally."),
            ("adb reboot recovery", "Restart directly into Android Recovery mode."),
            ("adb reboot bootloader", "Restart into Fastboot/Bootloader mode."),
        ]
        for command, purpose in entries:
            tree.insert("", "end", values=(command, purpose))
        scroll = ttk.Scrollbar(self.reference_tab, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _device_changed(self, _event: object = None) -> None:
        value = self.device_var.get()
        self.selected_serial = value.split(" ", 1)[0] if value else ""
        if self.selected_serial:
            self.load_device_info()

    def _run_async(self, label: str, fn: Callable[[], object]) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_var.set(f"{label}…")

        def worker() -> None:
            try:
                result = fn()
                self.events.put(("result", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def _process_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "result":
                    self._handle_result(payload)
                elif kind == "hotplug_changed":
                    self._show_devices(payload)
                elif kind == "error":
                    self._append_console(f"ERROR: {payload}")
                elif kind == "done":
                    self.busy = False
                    self.status_var.set("Ready")
        except queue.Empty:
            pass
        self.after(100, self._process_events)

    def _handle_result(self, payload: object) -> None:
        if isinstance(payload, tuple) and payload:
            tag = payload[0]
            if tag == "devices":
                self._show_devices(payload[1])
            elif tag == "info":
                self._show_device_info(payload[1])
            elif tag == "packages":
                self._show_packages(payload[1])
            elif tag == "text":
                self._append_console(str(payload[1]))
                self._append_tools(str(payload[1]))
            elif tag == "reload_packages":
                self._append_tools(str(payload[1]))
                # Automatically reload package list to reflect new state
                self.load_packages()

    def refresh_devices(self) -> None:
        self._run_async("Checking devices", lambda: ("devices", self.client.devices()))

    def _show_devices(self, result: AdbResult) -> None:
        devices: list[str] = []
        raw_lines: list[str] = []
        if result.code == 0:
            for line in result.stdout.splitlines()[1:]:
                if not line.strip():
                    continue
                raw_lines.append(line.strip())
                parts = line.split()
                serial = parts[0]
                state = parts[1] if len(parts) > 1 else "unknown"
                details = " ".join(parts[2:])
                devices.append(f"{serial} [{state}] {details}".strip())
        self._last_detected_devices = raw_lines
        self.device_combo["values"] = devices
        if devices:
            # Preserve current selection if still connected
            curr = self.device_var.get()
            if curr not in devices:
                self.device_combo.current(0)
                self._device_changed()
            self.status_var.set(f"{len(devices)} device(s) connected")
            if hasattr(self, "guide_step"):
                self.guide_step = 4
                self._update_guide()
        else:
            self.selected_serial = ""
            self.device_var.set("")
            self.device_info_var.set("No authorized device detected")
            self.status_var.set("Connect phone and enable USB debugging")
            if hasattr(self, "guide_step"):
                self.guide_step = 3
                self._update_guide()
            if result.stderr:
                self._append_console(result.stderr)

    def load_device_info(self) -> None:
        serial = self.selected_serial
        self._run_async("Reading device details", lambda: ("info", self._get_info(serial)))

    def _get_info(self, serial: str) -> dict[str, str]:
        props = {}
        for key in (
            "ro.product.manufacturer",
            "ro.product.model",
            "ro.build.version.release",
            "ro.build.version.sdk",
        ):
            result = self.client.shell(serial, "getprop", key)
            props[key] = result.stdout
        return props

    def _show_device_info(self, info: dict[str, str]) -> None:
        model = " ".join(filter(None, (info.get("ro.product.manufacturer"), info.get("ro.product.model"))))
        version = info.get("ro.build.version.release", "unknown")
        sdk = info.get("ro.build.version.sdk", "unknown")
        self.device_info_var.set(f"{model or 'Android Device'} · Android {version} (SDK {sdk})")

    def load_packages(self) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect and authorize an Android device first.")
            return
        serial = self.selected_serial
        self._run_async("Loading packages and safety ratings", lambda: ("packages", self.client.package_list_full(serial)))

    def _show_packages(self, packages: dict[str, PackageItem]) -> None:
        self.packages_data = packages
        self._filter_packages()
        safe_count = sum(1 for p in packages.values() if p.safety == "Safe")
        disabled_count = sum(1 for p in packages.values() if p.status in ("Disabled", "Uninstalled (User 0)"))
        self._append_tools(f"Loaded {len(packages)} packages. Found {safe_count} safe debloat targets; {disabled_count} currently inactive.")

        # Update Child-Safe Play Store status
        vending = packages.get("com.android.vending") or packages.get("com.google.android.vending")
        if vending and vending.status == "Enabled":
            self.play_store_status_var.set("Play Store: ACTIVE (Phone is Unlocked)")
            self.play_store_btn_var.set("🛡️ Lock Phone (Hide Play Store)")
        else:
            self.play_store_status_var.set("Play Store: LOCKED / HIDDEN (Child-Safe Active)")
            self.play_store_btn_var.set("🔓 Unlock Phone (Restore Play Store)")

    def _filter_packages(self) -> None:
        if not self.packages_data:
            return

        query = self.search_var.get().lower().strip()
        filter_mode = self.filter_var.get()

        all_rows: list[PackageItem] = []
        system_rows: list[PackageItem] = []
        user_rows: list[PackageItem] = []

        for item in self.packages_data.values():
            # Search match
            if query and not (query in item.package.lower() or query in item.name.lower() or query in item.category.lower()):
                continue

            # Category / Status filter match
            if filter_mode == "Safe Bloatware" and item.safety != "Safe":
                continue
            elif filter_mode == "Caution / Optional" and item.safety != "Caution":
                continue
            elif filter_mode == "Carrier Bloat" and item.category != "Carrier":
                continue
            elif filter_mode == "OEM (Samsung/Xiaomi)" and item.category not in ("Samsung", "Xiaomi", "OEM"):
                continue
            elif filter_mode == "Telemetry & Ads" and item.category != "Telemetry":
                continue
            elif filter_mode == "Disabled / Uninstalled" and item.status not in ("Disabled", "Uninstalled (User 0)"):
                continue

            all_rows.append(item)
            if item.is_system:
                system_rows.append(item)
            else:
                user_rows.append(item)

        self._render_tree(self.all_tree, all_rows)
        self._render_tree(self.system_tree, system_rows)
        self._render_tree(self.user_tree, user_rows)

        self.app_tabs.tab(0, text=f"All apps ({len(all_rows)})")
        self.app_tabs.tab(1, text=f"System apps ({len(system_rows)})")
        self.app_tabs.tab(2, text=f"User apps ({len(user_rows)})")

    def _render_tree(self, tree: ttk.Treeview, items: list[PackageItem]) -> None:
        tree.delete(*tree.get_children())
        for item in items:
            safety_display = f"🟢 Safe" if item.safety == "Safe" else f"🟡 Caution" if item.safety == "Caution" else f"🔴 Essential" if item.safety == "Essential" else "Unknown"
            tree.insert(
                "",
                "end",
                values=(item.name, safety_display, item.status, item.category, item.package),
            )

    def select_recommended_bloat(self) -> None:
        """Selects all packages matching 'Safe' debloat rating in the currently active tab."""
        self.package_tree.selection_set()
        to_select = []
        for child in self.package_tree.get_children():
            pkg = self.package_tree.item(child, "values")[4]
            item = self.packages_data.get(pkg)
            if item and item.safety == "Safe":
                to_select.append(child)
        if to_select:
            self.package_tree.selection_set(to_select)
            self.package_tree.see(to_select[0])
            messagebox.showinfo("Bloatware Selected", f"Selected {len(to_select)} recommended safe bloatware package(s).")
        else:
            messagebox.showinfo("No Bloatware", "No packages flagged as Safe Bloatware in current view.")

    def _selected_packages(self) -> list[str]:
        return [self.package_tree.item(item, "values")[4] for item in self.package_tree.selection()]

    def _check_critical_safeguards(self, packages: list[str]) -> bool:
        """Protects against bricking launchers, keyboards, or protected core services."""
        unsafe = [
            p for p in packages
            if (p.startswith(PROTECTED_PREFIXES) or (p in self.packages_data and self.packages_data[p].safety == "Essential"))
            and not p.endswith(".vending")
        ]
        if unsafe:
            messagebox.showerror(
                "Protected System Package",
                f"The following package(s) are essential to Android operation and cannot be modified:\n\n" + "\n".join(unsafe[:5]),
            )
            return False

        # Check for keyboard or launcher keywords
        critical_warnings = [
            p for p in packages
            if any(term in p.lower() for term in ("launcher", "inputmethod", "keyboard", "ime"))
        ]
        if critical_warnings:
            if not messagebox.askyesno(
                "Critical Component Warning",
                f"You selected a launcher or keyboard package:\n\n"
                + "\n".join(critical_warnings)
                + "\n\nDisabling or removing your only keyboard or home launcher can make it difficult to operate the phone.\nDo you still wish to proceed?",
            ):
                return False

        return True

    def change_selected(self, action: str) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select one or more packages first.")
            return

        if not self._check_safeguards(packages):
            return

        # STAGE 1 FIX: Use 'pm disable-user --user 0' for disabling on non-root Android
        commands = []
        for p in packages:
            if action == "disable":
                commands.append(["pm", "disable-user", "--user", "0", p])
            else:
                commands.append(["pm", "enable", p])

        self._confirm_and_run(commands, f"{action.title()} {len(packages)} package(s)?")

    def _check_safeguards(self, packages: list[str]) -> bool:
        return self._check_critical_safeguards(packages)

    def uninstall_selected(self) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select one or more packages first.")
            return

        if not self._check_safeguards(packages):
            return

        # Uninstall for user 0 preserves the system image while removing all user data & processes
        commands = [["pm", "uninstall", "--user", "0", p] for p in packages]
        self._confirm_and_run(commands, f"Uninstall {len(packages)} package(s) for the current user? (Can be restored later if system APK is present)")

    def restore_selected(self) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select one or more packages to restore.")
            return

        commands = [["cmd", "package", "install-existing", p] for p in packages]
        self._confirm_and_run(commands, f"Restore {len(packages)} uninstalled app(s) for current user?")

    def force_stop_selected(self) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select a package to force stop.")
            return
        commands = [["am", "force-stop", p] for p in packages]
        self._confirm_and_run(commands, f"Force stop running processes for {len(packages)} app(s)?")

    def clear_data_selected(self) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select a package to clear data.")
            return
        commands = [["pm", "clear", p] for p in packages]
        self._confirm_and_run(commands, f"Clear app storage and cache for {len(packages)} package(s)? This resets app data.")

    def lock_play_store(self) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect and authorize an Android device first.")
            return
        commands = [
            ["pm", "disable-user", "--user", "0", "com.android.vending"],
            ["pm", "uninstall", "--user", "0", "com.android.vending"]
        ]
        self._confirm_and_run(
            commands,
            "🛡️ CHILD-SAFE LOCK:\nHide & Uninstall Google Play Store (com.android.vending) for user 0?\n\n"
            "The Play Store icon will disappear from the phone so the child cannot browse or download apps.\n"
            "You can restore it anytime with one click (no APK needed)."
        )

    def restore_play_store(self) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect and authorize an Android device first.")
            return
        commands = [
            ["cmd", "package", "install-existing", "com.android.vending"],
            ["pm", "enable", "com.android.vending"]
        ]
        self._confirm_and_run(
            commands,
            "🔓 UNLOCK & RESTORE GOOGLE PLAY STORE:\nReinstall and enable Google Play Store (com.android.vending) from the phone's internal system partition?\n\n"
            "This will bring the Play Store back immediately with zero APK download required."
        )

    def toggle_play_store(self) -> None:
        vending = self.packages_data.get("com.android.vending") or self.packages_data.get("com.google.android.vending")
        if vending and vending.status == "Enabled":
            self.lock_play_store()
        else:
            self.restore_play_store()

    def run_reboot(self, mode: str) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect an authorized device first.")
            return
        args = ["-s", self.selected_serial, "reboot"]
        if mode:
            args.append(mode)
        prompt = f"Reboot device {self.selected_serial} {'to ' + mode if mode else 'normally'}?"
        if not messagebox.askyesno("Confirm Reboot", prompt):
            return
        self._run_async("Rebooting device", lambda: ("text", self.client.run(args).stdout or "Reboot signal sent"))

    def _confirm_and_run(self, commands: list[list[str]], prompt: str) -> None:
        preview = "\n".join("adb -s " + self.selected_serial + " shell " + " ".join(cmd) for cmd in commands)
        if not messagebox.askyesno("Confirm operation", f"{prompt}\n\nCommands to run:\n{preview}"):
            return
        serial = self.selected_serial
        # Auto reload package list after operations complete
        self._run_async("Executing operation", lambda: ("reload_packages", self._run_shell_commands(serial, commands)))

    def _run_shell_commands(self, serial: str, commands: list[list[str]]) -> str:
        lines = []
        for command in commands:
            result = self.client.shell(serial, *command)
            lines.append(f"$ adb -s {serial} shell {' '.join(command)}")
            lines.append(result.stdout or result.stderr or f"exit code {result.code}")
        return "\n".join(lines)

    def install_apk(self) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect and authorize an Android device first.")
            return
        path = filedialog.askopenfilename(filetypes=[("Android package", "*.apk"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askyesno("Confirm APK installation", f"Install this APK on {self.selected_serial}?\n\n{path}"):
            return
        serial = self.selected_serial
        self._run_async("Installing APK", lambda: ("text", self._install(serial, path)))

    def _install(self, serial: str, path: str) -> str:
        result = self.client.run(["-s", serial, "install", "-r", path], timeout=120)
        return f"$ adb -s {serial} install -r {path}\n{result.stdout or result.stderr or 'exit code ' + str(result.code)}"

    def export_packages(self) -> None:
        if not self.packages_data:
            messagebox.showinfo("Nothing to export", "Load installed apps first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = {
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "device": self.selected_serial,
            "packages": [
                {
                    "package": item.package,
                    "name": item.name,
                    "status": item.status,
                    "safety": item.safety,
                    "category": item.category,
                }
                for item in self.packages_data.values()
            ],
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._append_tools(f"Exported {len(self.packages_data)} packages to {path}")

    def import_packages(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            pkgs = data.get("packages", [])
            self.search_var.set("")
            self.filter_var.set("All Packages")
            # Populate review items
            self.packages_data = {
                p.get("package", str(p)): PackageItem(
                    package=p.get("package", str(p)),
                    name=p.get("name", str(p)),
                    is_system=True,
                    status=p.get("status", "Review"),
                    safety=p.get("safety", "Unknown"),
                    category=p.get("category", "General"),
                    description="Imported from file for review.",
                )
                for p in pkgs
            }
            self._filter_packages()
            self._append_tools(f"Loaded {len(self.packages_data)} packages from {path} for review.")
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Import failed", str(exc))

    def run_console(self) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect and authorize an Android device first.")
            return
        raw = self.console_var.get().strip()
        if not raw:
            return
        try:
            args = shlex.split(raw, posix=False)
            args = [arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'" else arg for arg in args]
        except ValueError:
            messagebox.showerror("Invalid command", "Unable to parse the command. Check quotation marks.")
            return
        if not args:
            return
        shell_mode = self.console_mode_var.get() == "Phone shell command"
        prefix = "adb -s " + self.selected_serial + (" shell " if shell_mode else " ")
        preview = prefix + " ".join(args)
        warning = "\n\nThis is an advanced command. It can modify phone settings or files."
        if not messagebox.askyesno("Run advanced command?", preview + warning):
            return
        serial = self.selected_serial
        self._run_async("Running console command", lambda: ("text", self._console(serial, args, shell_mode)))

    def _console(self, serial: str, args: list[str], shell_mode: bool) -> str:
        if shell_mode:
            result = self.client.shell(serial, *args, timeout=60)
            command = f"adb -s {serial} shell {' '.join(args)}"
        else:
            result = self.client.run(["-s", serial, *args], timeout=60)
            command = f"adb -s {serial} {' '.join(args)}"
        return f"$ {command}\n{result.stdout or result.stderr or 'exit code ' + str(result.code)}"

    def _append_console(self, text: str) -> None:
        self.console_output.configure(state="normal")
        self.console_output.insert("end", text + "\n\n")
        self.console_output.see("end")
        self.console_output.configure(state="disabled")

    def _append_tools(self, text: str) -> None:
        self.tools_log.configure(state="normal")
        self.tools_log.insert("end", text + "\n\n")
        self.tools_log.see("end")
        self.tools_log.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
