# CLAUDE.md - Project Context

## Quick Reference

**Project**: PicPlotter Auto (Web/Drive edition)
**Repo**: `PicPlotter_web_claude`
**Purpose**: Auto-plot geotagged photos on Google satellite imagery and export KMZ/HTML. Supports Google Drive folder import with URL-referenced web deployments.
**Status**: Feature complete, v3.0.0
**Related Docs**: [PLANNING.md](./PLANNING.md) | [TASKS.md](./TASKS.md)

---

## Development Workflow (IMPORTANT)

**Single source of truth (WSL):**
```
/home/rkinder9168/projects/PicPlotter_web_claude/
```

**Windows accesses WSL directly via network path:**
```
\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_web_claude\
```

### Workflow
1. **Code in WSL** - All development and git operations happen in WSL
2. **Test on Windows** - Run directly from WSL path:
   ```cmd
   cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_web_claude
   python -m src.main
   ```
3. **Build on Windows** - PyInstaller via build script:
   ```cmd
   cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_web_claude
   python build/build.py
   ```
4. **CI Build** - GitHub Actions `Build Installers` workflow (manual dispatch) creates Windows `.exe` installer and macOS `.dmg`, attached to a GitHub Release.

---

## Project Overview

PicPlotter Auto uses a tile-based Google satellite editor to adjust markers and rotation, then exports a single-file offline HTML deliverable (2k snapshot). Marker adjustments apply to KMZ exports.

### Key Value Proposition
- **Automatic map placement** - no manual calibration clicks
- **Manual corrections** - drag markers for fine-tuning
- **Google Drive import** - load photos from shared folders; web deploys use URL references (no download/re-upload)
- **KMZ and HTML exports** - deliver to Google Earth Pro or clients
- **Deploy to Web** - Netlify deployment with shareable link
- **Single executable** - one .exe to distribute

---

## Project Structure

```
/home/rkinder9168/projects/PicPlotter_web_claude/
├── src/
│   ├── __init__.py             # Package marker + version
│   ├── main.py                 # Entry point + single-window pywebview UI
│   ├── config.py               # API key config, constants, get_asset_path()
│   ├── exif_extractor.py       # GPS coordinate extraction from EXIF
│   ├── image_processor.py      # HEIC conversion, compression, EXIF orientation
│   ├── kmz_generator.py        # KML/KMZ generation with embedded images
│   ├── html_map_generator.py   # HTML map export with interactive markers
│   ├── google_drive.py         # Google Drive API client (folder listing, URLs, download)
│   ├── marker_utils.py         # Marker colorization (NumPy vectorized)
│   ├── photo_groups.py         # Photo group management
│   ├── coordinate_transform.py # PixelPoint and AffineTransform helpers
│   ├── netlify_deployer.py     # Netlify deployment for web sharing
│   └── utils.py                # File/folder utilities
├── assets/
│   ├── marker_outlined_transparent.png
│   └── app.html
├── build/
│   └── build.py                # Cross-platform PyInstaller build script
├── packaging/
│   ├── windows/PicPlotterAuto.iss  # Inno Setup installer script
│   └── macos/build_dmg.sh          # macOS DMG builder
├── .github/workflows/build.yml # CI: build installers on manual dispatch
├── PicPlotter.spec             # PyInstaller spec (local Windows build)
├── requirements.txt            # Python dependencies
├── build_windows.bat           # One-click Windows build
├── run.bat                     # Run from source (development)
├── README.md                   # User documentation
└── CLAUDE.md                   # This file
```

---

## Module Responsibilities

### `src/main.py`
- Single-window pywebview UI for selection, options, and editor
- Opens the map editor when requested from the main screen
- `import_from_drive()` - imports photos from shared Google Drive folders
- Handles KMZ and HTML export using saved marker overrides
- Web deploy uses Drive image URLs (no download) when all photos are from Drive
- Parallel photo processing with ThreadPoolExecutor

### `src/google_drive.py`
- Google Drive API v3 client using stdlib `urllib` (no extra dependencies)
- `parse_drive_folder_url()` - extracts folder ID from sharing URLs
- `list_folder_images()` - lists images with pagination
- `get_image_url()` / `get_thumbnail_url()` - public CDN URLs for shared files
- `fetch_image_bytes()` - full/partial file download for local exports
- `extract_metadata_from_drive()` - EXIF extraction from partial download

### `src/config.py`
- Saves/loads Google API keys and Netlify tokens from `~/.picplotter_auto/config.json`
- Environment variable fallback (`GOOGLE_MAPS_API_KEY`)
- Centralized constants (TILE_SIZE, EXPORT_MAX_DIM, etc.)
- Shared `get_asset_path()` for PyInstaller compatibility

### `src/exif_extractor.py`
- Extracts GPS, timestamp, camera info from EXIF in a single file open
- `get_image_metadata_from_bytes()` for in-memory EXIF extraction (Drive photos)
- Handles JPG and HEIC formats

### `src/html_map_generator.py`
- Generates interactive HTML maps with aerial background and photo markers
- Supports both base64-embedded photos (`image_data`) and URL-referenced photos (`image_url`)

---

## Dependencies

```
pillow>=10.0.0       # Image processing
pillow-heif>=0.16.0  # HEIC/HEIF support
numpy>=1.20.0        # Vectorized marker colorization
pywebview>=4.0       # Embedded map editor
pyinstaller>=6.0     # Executable creation (build only)
```

No additional dependencies for Google Drive support (uses stdlib `urllib`).

---

## WSL vs Windows

- **Development**: WSL (`/home/rkinder9168/projects/PicPlotter_web_claude/`)
- **Testing/Building**: Windows reads WSL files directly via `\\wsl$\Ubuntu\...`
- **CI**: GitHub Actions builds on `windows-latest` and `macos-latest`
