# Packaging and Distribution

This folder contains scripts and templates for producing Windows and macOS installers.
Builds must be created on the target OS (no cross-compile).

## Versioning

The app version is read from `src/__init__.py` (`__version__`).
Installer/DMG filenames use the version, with `-auto` stripped if present.

## Windows (Inno Setup)

1. Build the app:
   - Run `build_windows.bat` or `python build/build.py`
   - Output: `dist/PicPlotterAuto.exe`
2. Open `packaging/windows/PicPlotterAuto.iss` in Inno Setup and compile.
3. Installer output: `dist/installer/PicPlotterAuto-<version>-Setup.exe`

Notes:
- No code-signing certificate means Windows SmartScreen warnings.
- The installer is per-user (no admin) and creates Start Menu + Desktop shortcuts.

## macOS (DMG)

1. Build the app on macOS:
   - Run `python3 build/build.py`
   - Output: `dist/PicPlotterAuto.app`
2. Run `packaging/macos/build_dmg.sh`
3. DMG output: `dist/PicPlotterAuto-<version>.dmg`

Notes:
- Without a signing certificate, Gatekeeper will require right-click -> Open on first run.
- For a custom macOS icon, add `assets/icon.icns` before building.

## API Key Behavior

No API key is bundled. Each user enters their key in the app and it is saved to:
`~/.picplotter_auto/config.json`

## GitHub Actions (Click Build)

Manual builds are available in GitHub Actions:
- Workflow: `Build Installers` (`.github/workflows/build.yml`)
- Trigger: Actions tab → Build Installers → Run workflow

Artifacts:
- Windows: `PicPlotterAuto-<version>-Setup.exe`
- macOS: `PicPlotterAuto-<version>.dmg`
