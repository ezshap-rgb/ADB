# ADB Device Manager & Debloater

A clean, powerful Windows desktop UI for Android Debug Bridge tools and bloatware management.

## Run

Install Python 3.10 or newer, then double-click `run_adb_manager.bat` or run:

```powershell
py adb_manager.py
```

The application expects `platform-tools/adb.exe` beside the Python file (bundled revision 31.0.3).

## Phone Setup

1. On the phone, open **Settings > About phone** and tap **Build number** 7 times.
2. Go to **Settings > Developer options** and turn on **USB debugging**.
3. Connect the phone by USB cable.
4. Accept the computer authorization prompt on the phone screen.
5. The app automatically detects connected devices with live hotplug detection.

## Features & Improvements

- **Accurate Package State Detection**: Live tracking of **Enabled**, **Disabled**, and **Uninstalled (User 0)** packages using multi-flag package queries (`-a`, `-s`, `-3`, `-d`, `-e`, `-u`).
- **Debloating Intelligence**: Built-in curated database classifying packages into **Safe**, **Caution**, and **Essential** tiers across Google, Samsung, Xiaomi, Carrier, and Telemetry/Ad services.
- **One-Click Bloatware Selection**: Quickly highlight and select recommended safe bloatware packages with a single click.
- **Category Filtering**: Filter by *Safe Bloatware*, *Carrier Bloat*, *OEM (Samsung/Xiaomi)*, *Telemetry & Ads*, or *Disabled / Inactive*.
- **Package Inspector**: Select any package to review its full description, category, safety rating, and APK path.
- **Critical Safeguards**: Blocks deletion of core Android components and explicitly alerts before modifying active launchers or keyboards to prevent accidental lockout.
- **Non-Root Safe Execution**: Uses `pm disable-user --user 0` instead of root-only commands, ensuring flawless execution on standard devices.
- **Device Diagnostics & Reboot**: One-click shortcuts to restart normally, reboot into **Recovery**, or reboot into **Fastboot/Bootloader**.
- **Quick App Controls**: Force-stop running processes or clear application cache and data in one click.
- **Automatic USB Hotplug**: Automatically recognizes device plug/unplug events without needing manual refreshes.
- **Advanced Shell Console**: Run direct phone shell commands or raw ADB arguments with full output history.
- **Import/Export Profiles**: Save and review package snapshots in JSON format.

> [!NOTE]
> This tool does not require root and does not alter bootloader locks. All user-level uninstalls retain the underlying system APK in `/system` and can be restored at any time via `cmd package install-existing`.
