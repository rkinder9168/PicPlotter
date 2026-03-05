# CLAUDE.md - Project Context

## Quick Reference

**Project**: PicPlotter Auto
**Purpose**: Auto-plot geotagged photos on Google satellite imagery and export KMZ/HTML
**Status**: In progress
**Related Docs**: [PLANNING.md](./PLANNING.md) | [TASKS.md](./TASKS.md)

---

## Development Workflow (IMPORTANT)

**Single source of truth (WSL):**
```
/home/rkinder9168/projects/PicPlotter_auto_gpt/
```

**Windows accesses WSL directly via network path:**
```
\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_auto_gpt\
```

### Workflow
1. **Code in WSL** - All development and git operations happen in WSL
2. **Test on Windows** - Run directly from WSL path:
   ```cmd
   cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_auto_gpt
   python src/main.py
   ```
3. **Build on Windows** - PyInstaller runs from WSL path:
   ```cmd
   cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_auto_gpt
   pyinstaller PicPlotter.spec --clean
   ```

---

## Project Overview

PicPlotter Auto uses a tile-based Google satellite editor to adjust markers and rotation, then exports a single-file offline HTML deliverable (2k snapshot). Marker adjustments apply to KMZ exports.

### Key Value Proposition
- **Automatic map placement** - no manual calibration clicks
- **Manual corrections** - drag markers for fine-tuning
- **KMZ and HTML exports** - deliver to Google Earth Pro or clients
- **Single executable** - one .exe to distribute

---

## Project Structure

```
/home/rkinder9168/projects/PicPlotter_auto_gpt/
├── src/
│   ├── __init__.py           # Package marker + version
│   ├── main.py               # Entry point + single-window pywebview UI
│   ├── config.py             # API key config, constants, get_asset_path()
│   ├── exif_extractor.py     # GPS coordinate extraction from EXIF
│   ├── image_processor.py    # HEIC conversion, compression, EXIF orientation
│   ├── kmz_generator.py      # KML/KMZ generation with embedded images
│   ├── html_map_generator.py # HTML map export with interactive markers
│   ├── marker_utils.py       # Marker colorization (NumPy vectorized)
│   ├── photo_groups.py       # Photo group management
│   ├── coordinate_transform.py # PixelPoint and AffineTransform helpers
│   ├── netlify_deployer.py   # Netlify deployment for web sharing
│   └── utils.py              # File/folder utilities
├── assets/
│   ├── marker_outlined_transparent.png
│   └── app.html
├── PicPlotter.spec           # PyInstaller spec file
├── requirements.txt          # Python dependencies
├── build_windows.bat         # One-click Windows build
├── run.bat                   # Run from source (development)
├── README.md                 # User documentation
└── CLAUDE.md                 # This file
```

---

## Module Responsibilities

### `src/main.py`
- Single-window pywebview UI for selection, options, and editor
- Opens the map editor when requested from the main screen
- Handles KMZ and HTML export using saved marker overrides
- Parallel photo processing with ThreadPoolExecutor

### `src/config.py`
- Saves/loads Google API keys and Netlify tokens from `~/.picplotter_auto/config.json`
- Environment variable fallback (`GOOGLE_MAPS_API_KEY`)
- Centralized constants (TILE_SIZE, EXPORT_MAX_DIM, etc.)
- Shared `get_asset_path()` for PyInstaller compatibility

### `src/exif_extractor.py`
- Extracts GPS, timestamp, camera info from EXIF in a single file open
- Handles JPG and HEIC formats

---

## Dependencies

```
pillow>=10.0.0       # Image processing
pillow-heif>=0.16.0  # HEIC/HEIF support
numpy>=1.20.0        # Vectorized marker colorization
pywebview>=4.0       # Embedded map editor
pyinstaller>=6.0     # Executable creation (build only)
```

---

## WSL vs Windows

- **Development**: WSL (`/home/rkinder9168/projects/PicPlotter_auto_gpt/`)
- **Testing/Building**: Windows reads WSL files directly via `\\wsl$\Ubuntu\...`
