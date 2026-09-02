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

APP_NAME_OVERRIDES = {
    "com.android.chrome": "Google Chrome",
    "com.google.android.youtube": "YouTube",
    "com.google.android.vending": "Google Play Store",
    "com.google.android.gms": "Google Play services",
    "com.google.android.gsf": "Google Services Framework",
    "com.google.android.googlequicksearchbox": "Google app",
    "com.google.android.apps.photos": "Google Photos",
    "com.google.android.gm": "Gmail",
    "com.google.android.apps.maps": "Google Maps",
    "com.android.settings": "Settings",
    "com.android.systemui": "System UI",
}

# Packages that should never be offered by the curated UI.
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

    def package_list(self, serial: str) -> tuple[AdbResult, AdbResult, AdbResult]:
        # Read all known packages and separately ask Android which are system
        # and third-party packages so the UI can label them accurately.
        all_packages = self.shell(serial, "pm", "list", "packages", "-a")
        system_packages = self.shell(serial, "pm", "list", "packages", "-s")
        user_packages = self.shell(serial, "pm", "list", "packages", "-3")
        return all_packages, system_packages, user_packages


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ADB Device Manager")
        self.geometry("980x680")
        self.minsize(760, 500)
        self.client = AdbClient()
        self.selected_serial = ""
        self.package_rows: list[tuple[str, str]] = []
        self.package_state: dict[str, str] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self._build_style()
        self._build_ui()
        self.after(100, self._process_events)
        self.after(250, self.refresh_devices)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", foreground="#666666")
        style.configure("Danger.TButton", foreground="#9b1c1c")

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(18, 14, 18, 8))
        header.pack(fill="x")
        ttk.Label(header, text="ADB Device Manager", style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="Starting…")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        device_bar = ttk.LabelFrame(self, text="Device", padding=10)
        device_bar.pack(fill="x", padx=18, pady=(0, 10))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_bar, textvariable=self.device_var, state="readonly", width=54)
        self.device_combo.pack(side="left", padx=(0, 8))
        self.device_combo.bind("<<ComboboxSelected>>", self._device_changed)
        ttk.Button(device_bar, text="Refresh", command=self.refresh_devices).pack(side="left")
        self.device_info_var = tk.StringVar(value="No device selected")
        ttk.Label(device_bar, textvariable=self.device_info_var, style="Muted.TLabel").pack(side="left", padx=18)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.apps_tab = ttk.Frame(self.tabs, padding=10)
        self.tools_tab = ttk.Frame(self.tabs, padding=10)
        self.console_tab = ttk.Frame(self.tabs, padding=10)
        self.reference_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.apps_tab, text="Apps")
        self.tabs.add(self.tools_tab, text="Tools")
        self.tabs.add(self.console_tab, text="Advanced console")
        self.tabs.add(self.reference_tab, text="Command reference")
        self._build_guide_tab()
        self._build_apps_tab()
        self._build_tools_tab()
        self._build_console_tab()
        self._build_reference_tab()

    def _build_reference_tab(self) -> None:
        ttk.Label(self.reference_tab, text="ADB and phone-shell command reference", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.reference_tab, text="These examples are informational. Run them from the Advanced console only when you understand the result.", style="Muted.TLabel", wraplength=850).pack(anchor="w", pady=(4, 10))
        columns = ("command", "purpose")
        tree = ttk.Treeview(self.reference_tab, columns=columns, show="headings")
        tree.heading("command", text="Command")
        tree.heading("purpose", text="What it does")
        tree.column("command", width=430, anchor="w")
        tree.column("purpose", width=500, anchor="w")
        entries = [
            ("adb devices -l", "List connected devices and their connection state."),
            ("adb shell getprop ro.product.model", "Show the phone model."),
            ("adb shell pm list packages", "List packages visible to Android."),
            ("adb shell pm list packages -s", "List system packages."),
            ("adb shell pm list packages -3", "List third-party/user-installed packages."),
            ("adb shell pm path PACKAGE", "Show the APK path for a package."),
            ("adb shell pm clear PACKAGE", "Erase an app's data; does not uninstall it."),
            ("adb shell pm disable-user --user 0 PACKAGE", "Disable a package for user 0; usually reversible."),
            ("adb shell pm enable PACKAGE", "Enable a previously disabled package."),
            ("adb shell pm uninstall --user 0 PACKAGE", "Remove a package for user 0 while retaining the system copy when possible."),
            ("adb shell cmd package install-existing PACKAGE", "Restore a package removed only for the current user."),
            ("adb install -r FILE.apk", "Install or update an APK while retaining app data when possible."),
            ("adb reboot", "Restart the phone normally."),
        ]
        for command, purpose in entries:
            tree.insert("", "end", values=(command, purpose))
        scroll = ttk.Scrollbar(self.reference_tab, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_guide_tab(self) -> None:
        self.guide_tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.insert(0, self.guide_tab, text="Getting started")
        ttk.Label(self.guide_tab, text="Connect your Android phone", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.guide_tab, text="Follow these steps each time you use the program. You do not need to remember the setup.", style="Muted.TLabel").pack(anchor="w", pady=(4, 18))
        self.guide_status_var = tk.StringVar(value="Step 1 of 5")
        ttk.Label(self.guide_tab, textvariable=self.guide_status_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.guide_text = tk.Text(self.guide_tab, height=12, width=80, wrap="word", relief="flat", background=self.cget("background"))
        self.guide_text.pack(fill="x", pady=10)
        self.guide_text.configure(state="disabled")
        buttons = ttk.Frame(self.guide_tab)
        buttons.pack(fill="x")
        self.guide_back = ttk.Button(buttons, text="Back", command=lambda: self._guide_move(-1))
        self.guide_back.pack(side="left")
        self.guide_next = ttk.Button(buttons, text="Next", command=lambda: self._guide_move(1))
        self.guide_next.pack(side="left", padx=8)
        ttk.Button(buttons, text="Check connection", command=self.refresh_devices).pack(side="left")
        ttk.Button(buttons, text="Open Apps", command=lambda: self.tabs.select(self.apps_tab)).pack(side="right")
        self.guide_step = 0
        self._update_guide()

    def _guide_move(self, delta: int) -> None:
        self.guide_step = max(0, min(4, self.guide_step + delta))
        self._update_guide()

    def _update_guide(self) -> None:
        steps = [
            ("Prepare the phone", "Keep the phone unlocked and use a working USB data cable. Charge the phone if you will be making several changes."),
            ("Enable Developer options", "On the phone, open Settings > About phone. Tap Build number seven times. Confirm your screen lock if Android asks."),
            ("Enable USB debugging", "Open Settings > System > Developer options (the location varies by manufacturer), then turn on USB debugging."),
            ("Connect and authorize", "Connect the phone to this computer. Unlock it and choose Allow on the USB debugging prompt. Tick Always allow only if this is your personal computer."),
            ("Refresh and choose an action", "Click Check connection. Once the device appears above, load installed apps. Prefer Disable first because it is generally easier to reverse than uninstall."),
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
        top = ttk.Frame(self.apps_tab)
        top.pack(fill="x", pady=(0, 8))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_packages())
        ttk.Label(top, text="Search:").pack(side="left")
        ttk.Entry(top, textvariable=self.search_var, width=36).pack(side="left", padx=(6, 12))
        ttk.Button(top, text="Load installed apps", command=self.load_packages).pack(side="left")
        ttk.Button(top, text="Export list", command=self.export_packages).pack(side="left", padx=6)
        ttk.Button(top, text="Import list", command=self.import_packages).pack(side="left")

        app_content = ttk.Frame(self.apps_tab)
        app_content.pack(fill="both", expand=True)
        self.app_tabs = ttk.Notebook(app_content)
        self.app_tabs.pack(side="left", fill="both", expand=True)
        self.system_apps_tab = ttk.Frame(self.app_tabs, padding=(0, 8, 0, 0))
        self.user_apps_tab = ttk.Frame(self.app_tabs, padding=(0, 8, 0, 0))
        self.app_tabs.add(self.system_apps_tab, text="System apps")
        self.app_tabs.add(self.user_apps_tab, text="User apps")
        self.system_tree = self._create_package_tree(self.system_apps_tab)
        self.user_tree = self._create_package_tree(self.user_apps_tab)
        self.package_tree = self.system_tree
        self.app_tabs.bind("<<NotebookTabChanged>>", self._app_tab_changed)

        actions = ttk.LabelFrame(app_content, text="Actions", padding=8)
        actions.pack(side="right", fill="y", padx=(10, 0), pady=(8, 0))
        ttk.Button(actions, text="Enable selected", command=lambda: self.change_selected("enable"), width=20).pack(fill="x", pady=3)
        ttk.Button(actions, text="Disable selected", command=lambda: self.change_selected("disable"), width=20).pack(fill="x", pady=3)
        ttk.Button(actions, text="Uninstall selected", style="Danger.TButton", command=self.uninstall_selected, width=20).pack(fill="x", pady=3)
        ttk.Button(actions, text="Restore selected", command=self.restore_selected, width=20).pack(fill="x", pady=3)
        ttk.Separator(actions, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(actions, text="Select an app in the active tab.\n\nSystem apps can be important to phone functions. Review the confirmation command before proceeding.", style="Muted.TLabel", wraplength=145).pack(fill="x")

    def _create_package_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        content = ttk.Frame(parent)
        content.pack(fill="both", expand=True)
        columns = ("name", "package", "state")
        tree = ttk.Treeview(content, columns=columns, show="headings", selectmode="extended")
        tree.heading("name", text="App name")
        tree.heading("package", text="Package name")
        tree.heading("state", text="Status")
        tree.column("name", width=180, anchor="w")
        tree.column("package", width=470, anchor="w")
        tree.column("state", width=120, anchor="w")
        scroll = ttk.Scrollbar(content, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def _app_tab_changed(self, _event: object = None) -> None:
        self.package_tree = self.system_tree if self.app_tabs.index("current") == 0 else self.user_tree

    def _package_name(self, package: str) -> str:
        if package in APP_NAME_OVERRIDES:
            return APP_NAME_OVERRIDES[package]
        last = package.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ")
        return last.title() if last and last != package else package

    def _render_tree(self, tree: ttk.Treeview, rows: list[tuple[str, str]]) -> None:
        tree.delete(*tree.get_children())
        for package, state in rows:
            tree.insert("", "end", values=(self._package_name(package), package, state))


    def _build_tools_tab(self) -> None:
        box = ttk.LabelFrame(self.tools_tab, text="APK installation", padding=12)
        box.pack(fill="x", anchor="n")
        ttk.Label(box, text="Install an APK on the selected device. Android may show an authorization prompt.").pack(anchor="w")
        ttk.Button(box, text="Choose APK and install", command=self.install_apk).pack(anchor="w", pady=(10, 0))
        backup = ttk.LabelFrame(self.tools_tab, text="Backup / review", padding=12)
        backup.pack(fill="x", anchor="n", pady=12)
        ttk.Label(backup, text="Exported package lists are review files only; importing never changes the phone automatically.").pack(anchor="w")
        ttk.Button(backup, text="Export current app list", command=self.export_packages).pack(anchor="w", pady=(10, 0))
        self.tools_log = tk.Text(self.tools_tab, height=18, state="disabled", wrap="word")
        self.tools_log.pack(fill="both", expand=True, pady=(8, 0))

    def _build_console_tab(self) -> None:
        ttk.Label(self.console_tab, text="Advanced mode: manually enter a command. Shell mode is selected by default, so you can type commands such as: pm uninstall --user 0 com.example.app", style="Muted.TLabel", wraplength=900).pack(anchor="w")
        row = ttk.Frame(self.console_tab)
        row.pack(fill="x", pady=8)
        self.console_mode_var = tk.StringVar(value="Phone shell command")
        ttk.Combobox(row, textvariable=self.console_mode_var, state="readonly", width=24, values=("Phone shell command", "ADB command arguments")).pack(side="left", padx=(0, 8))
        self.console_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.console_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _: self.run_console())
        ttk.Button(row, text="Run command", command=self.run_console).pack(side="left", padx=(8, 0))
        self.console_output = tk.Text(self.console_tab, state="disabled", wrap="word")
        self.console_output.pack(fill="both", expand=True)

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
            except Exception as exc:  # UI must stay alive on unexpected ADB errors.
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
                elif kind == "error":
                    self._append_console(f"ERROR: {payload}")
                elif kind == "done":
                    self.busy = False
                    self.status_var.set("Ready")
        except queue.Empty:
            pass
        self.after(100, self._process_events)

    def _handle_result(self, payload: object) -> None:
        if isinstance(payload, tuple) and payload and payload[0] == "devices":
            self._show_devices(payload[1])
        elif isinstance(payload, tuple) and payload and payload[0] == "info":
            self._show_device_info(payload[1])
        elif isinstance(payload, tuple) and payload and payload[0] == "packages":
            self._show_packages(payload[1])
        elif isinstance(payload, tuple) and payload and payload[0] == "text":
            self._append_console(str(payload[1]))
            self._append_tools(str(payload[1]))

    def refresh_devices(self) -> None:
        self._run_async("Checking devices", lambda: ("devices", self.client.devices()))

    def _show_devices(self, result: AdbResult) -> None:
        devices: list[str] = []
        if result.code == 0:
            for line in result.stdout.splitlines()[1:]:
                if not line.strip():
                    continue
                parts = line.split()
                serial, state = parts[0], parts[1] if len(parts) > 1 else "unknown"
                details = " ".join(parts[2:])
                devices.append(f"{serial} [{state}] {details}".strip())
        self.device_combo["values"] = devices
        if devices:
            self.device_combo.current(0)
            self._device_changed()
            self.status_var.set(f"{len(devices)} device(s) detected")
            if hasattr(self, "guide_step"):
                self.guide_step = 4
                self._update_guide()
        else:
            self.selected_serial = ""
            self.device_info_var.set("No authorized device detected")
            self.status_var.set("Connect a phone and enable USB debugging")
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
        for key in ("ro.product.manufacturer", "ro.product.model", "ro.build.version.release", "ro.build.version.sdk"):
            result = self.client.shell(serial, "getprop", key)
            props[key] = result.stdout
        return props

    def _show_device_info(self, info: dict[str, str]) -> None:
        model = " ".join(filter(None, (info.get("ro.product.manufacturer"), info.get("ro.product.model"))))
        version = info.get("ro.build.version.release", "unknown")
        sdk = info.get("ro.build.version.sdk", "unknown")
        self.device_info_var.set(f"{model or 'Android device'} · Android {version} · SDK {sdk}")

    def load_packages(self) -> None:
        if not self.selected_serial:
            messagebox.showinfo("No device", "Connect and authorize an Android device first.")
            return
        serial = self.selected_serial
        self._run_async("Loading packages", lambda: ("packages", self.client.package_list(serial)))

    def _show_packages(self, results: tuple[AdbResult, AdbResult, AdbResult]) -> None:
        all_result, system_result, user_result = results
        if all_result.code != 0:
            self._append_console(all_result.stderr or all_result.stdout)
            return

        def parse(result: AdbResult) -> set[str]:
            return {line.removeprefix("package:").strip() for line in result.stdout.splitlines() if line.startswith("package:")}

        system_packages = parse(system_result)
        user_packages = parse(user_result)
        packages = sorted(parse(all_result), key=str.casefold)
        self.package_state = {
            package: ("system app" if package in system_packages else "user app" if package in user_packages else "installed")
            for package in packages
        }
        self.package_rows = [(package, self.package_state[package]) for package in packages]
        self._filter_packages()
        self._append_tools(f"Loaded {len(packages)} apps: {len(system_packages)} system, {len(user_packages)} user.")

    def _filter_packages(self) -> None:
        if not hasattr(self, "package_tree"):
            return
        query = self.search_var.get().lower()
        system_rows = []
        user_rows = []
        for package, state in self.package_rows:
            if query in package.lower() or query in self._package_name(package).lower():
                (system_rows if state == "system app" else user_rows).append((package, state))
        self._render_tree(self.system_tree, system_rows)
        self._render_tree(self.user_tree, user_rows)
        self.system_apps_tab.master.tab(0, text=f"System apps ({len(system_rows)})")
        self.system_apps_tab.master.tab(1, text=f"User apps ({len(user_rows)})")

    def _selected_packages(self) -> list[str]:
        return [self.package_tree.item(item, "values")[1] for item in self.package_tree.selection()]

    @staticmethod
    def _protected(package: str) -> bool:
        return package.startswith(PROTECTED_PREFIXES)

    def change_selected(self, action: str) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select one or more packages on an authorized device.")
            return
        unsafe = [p for p in packages if self._protected(p)]
        if unsafe:
            messagebox.showwarning("Protected packages", "The curated UI will not modify protected Android packages.")
            return
        commands = [["pm", action, p] for p in packages]
        self._confirm_and_run(commands, f"{action.title()} {len(packages)} package(s)?")

    def restore_selected(self) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select one or more package names on an authorized device.")
            return
        unsafe = [p for p in packages if self._protected(p)]
        if unsafe:
            messagebox.showwarning("Protected packages", "The curated UI will not restore protected Android packages.")
            return
        commands = [["cmd", "package", "install-existing", p] for p in packages]
        self._confirm_and_run(commands, "Restore selected apps for the current user? This only works if Android still has the system package.")

    def uninstall_selected(self) -> None:
        packages = self._selected_packages()
        if not packages or not self.selected_serial:
            messagebox.showinfo("Selection required", "Select one or more packages on an authorized device.")
            return
        unsafe = [p for p in packages if self._protected(p)]
        if unsafe:
            messagebox.showwarning("Protected packages", "The curated UI will not uninstall protected Android packages.")
            return
        commands = [["pm", "uninstall", "--user", "0", p] for p in packages]
        self._confirm_and_run(commands, "Uninstall selected packages for the current user? This may affect phone features.")

    def _confirm_and_run(self, commands: list[list[str]], prompt: str) -> None:
        preview = "\n".join("adb -s " + self.selected_serial + " shell " + " ".join(cmd) for cmd in commands)
        if not messagebox.askyesno("Confirm operation", f"{prompt}\n\nCommands:\n{preview}"):
            return
        serial = self.selected_serial
        self._run_async("Running operation", lambda: ("text", self._run_shell_commands(serial, commands)))

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
        if not self.package_rows:
            messagebox.showinfo("Nothing to export", "Load installed apps first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "device": self.selected_serial, "packages": [p for p, _ in self.package_rows]}
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._append_tools(f"Exported {len(self.package_rows)} packages to {path}")

    def import_packages(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            packages = data.get("packages", [])
            self.search_var.set("")
            self.package_rows = [(str(p), "review") for p in packages if isinstance(p, str)]
            self._filter_packages()
            self._append_tools(f"Loaded {len(self.package_rows)} packages for review; no device changes were made.")
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
        warning = "\n\nThis is an advanced command. It can change or damage the phone."
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
