# Kuro Commander

<p align="center">
  <img src="kuro.png" alt="Kuro Commander" width="400">
</p>

Kuro Commander is a small Windows utility for preparing local files and copying
them to an Android phone's Camera folder over ADB.

## What it does

- Select multiple files from the computer.
- Batch-rename selected files by adding a suffix before each extension.
- Copy selected files to `/storage/emulated/0/DCIM/Camera`.
- Detect rename and phone-copy conflicts before changing files.
- Request an Android media scan after copying so new files appear in gallery apps.
- Show copy progress, errors, and connection status without opening a command window.
- Use the bundled ADB tools or a custom `adb.exe` selected in Settings.

Renaming changes the original local files. Files that already have the selected
suffix and existing local rename targets are skipped. Before copying, the app
checks for same-name files on the phone and duplicate selected filenames, then
offers to overwrite, skip the conflicts, or cancel.

## Requirements

- Windows 10 or 11.
- An Android phone with USB debugging enabled.
- The computer authorized when the phone displays the USB debugging prompt.

## Run from source

Python 3.10 or newer is required. Start `run.bat`, or run:

```powershell
python kuro.py
```

## Build the executable

Install PyInstaller, then run the included build script:

```powershell
python -m pip install pyinstaller
.\build.ps1
```

The console-free, self-contained executable is created at:

```text
dist\KuroCommander.exe
```

The executable contains `adb.exe` and its required DLLs. It does not require a
separate Python installation.

## Settings

User settings are stored at:

```text
%LOCALAPPDATA%\KuroCommander\settings.json
```

The repository does not include generated builds, local settings, caches, or
backup files.

## Current scope

Kuro Commander works with selected local files. It is not a two-panel file
manager and does not currently select or recursively copy folders.
