# ADB Device Manager

A small Windows desktop UI for the bundled Android Debug Bridge tools.

## Run

Install Python 3.10 or newer, then double-click `run_adb_manager.bat` or run:

```powershell
py adb_manager.py
```

The application expects `platform-tools/adb.exe` beside the Python file. The supplied platform-tools revision is 31.0.3.

## Phone setup

1. On the phone, enable Developer options.
2. Enable USB debugging.
3. Connect the phone by USB.
4. Accept the computer authorization prompt on the phone.
5. Click **Refresh** in the app.

## Features

The app opens on a **Getting started** tab with a five-step setup guide. It explains how to enable Developer options, turn on USB debugging, authorize the computer, and check the connection. The guide updates automatically when a device is detected or when no authorized device is found, so you can return to the program months later without having to remember the process.

- Device connection and basic Android details.
- Full package listing and search, separated into System apps and User apps tabs.
- Friendly app-name column alongside each package name, with a safe package-based fallback when Android does not provide a label.
- Enable and disable selected packages.
- Uninstall packages for Android user 0.
- Restore a user-removed app with Android's `cmd package install-existing` command when the system package is still present.
- APK installation.
- Export/import package lists for review.
- Advanced console with a phone-shell mode for commands such as `pm uninstall --user 0 package.name`, plus an ADB-arguments mode.
- Command reference tab with common ADB and phone-shell commands and short explanations.

Every device-changing action displays the command and asks for confirmation. The Apps tab displays system packages, but blocks several core Android packages from its guided actions. The advanced console is intentionally powerful: use it only when you understand the command, and keep a backup of important data. For an app removed for user 0, a typical restoration command is `cmd package install-existing package.name`.

This tool does not root phones, bypass locks, or alter bootloader state.
