# TASKS.md - Task Tracking and Status

**Related Docs**: [CLAUDE.md](./CLAUDE.md) | [PLANNING.md](./PLANNING.md)

---

## Project Status: v3.0.0 - Feature Complete

All planned features implemented. Windows and macOS builds available via GitHub Actions.

**Current Notes**
- Single-window pywebview app with embedded tile-based editor view
- Google Drive folder import with URL-referenced web deployments
- Offline HTML export uses a stitched 2k snapshot (no API key required)
- Tile-based preview matches the export snapshot
- Manual placement for non-GPS photos and per-photo group labels in the editor
- CI builds Windows `.exe` installer and macOS `.dmg` on manual dispatch

---

## Completed Tasks

### Phase 1-6: Core App (inherited from PicPlotter_auto_gpt)
- [x] EXIF/GPS extraction (JPG + HEIC)
- [x] Image processing (resize, compress, orientation)
- [x] KMZ generation with embedded images
- [x] HTML map export with interactive markers
- [x] Single-window pywebview UI
- [x] PyInstaller build system
- [x] Photo groups with marker colorization
- [x] Manual placement for non-GPS photos
- [x] Netlify web deployment
- [x] Performance optimizations (parallel processing, NumPy markers)

### Phase 11: Google Drive URL References (v3.0.0)
- [x] New `src/google_drive.py` module (~230 lines, stdlib urllib only)
  - [x] `parse_drive_folder_url()` - extract folder ID from sharing URLs
  - [x] `validate_folder_access()` - test API key + folder access
  - [x] `list_folder_images()` - list images with pagination
  - [x] `get_image_url()` / `get_thumbnail_url()` - public CDN URLs
  - [x] `fetch_image_bytes()` - full/partial file download
  - [x] `get_drive_image_metadata()` - GPS from Drive API imageMediaMetadata
  - [x] `extract_metadata_from_drive()` - EXIF from partial download fallback
- [x] `src/exif_extractor.py` - added `get_image_metadata_from_bytes()`
- [x] `src/image_processor.py` - added `process_image_bytes()`
- [x] `src/main.py` changes:
  - [x] AppState: `drive_sources`, `drive_folder_url` fields
  - [x] `import_from_drive()` API method (parallel metadata extraction)
  - [x] `_get_photo_preview_uri()` returns Drive thumbnail URLs
  - [x] `deploy_to_web()` uses image URLs when all photos are from Drive
  - [x] `_process_single_photo()` handles Drive photos (download + process)
  - [x] `_run_kmz_export()` downloads Drive photos to temp files
  - [x] `_build_drive_photo_dicts()` / `_build_drive_custom_export()` for web deploy
  - [x] `clear_photos()` / `delete_photos()` clean up Drive state
- [x] `src/html_map_generator.py` - `image_url` support in photo dicts
- [x] `assets/app.html` - "Import from Drive" button + URL input panel + JS handler

### Phase 12: Build & CI Setup
- [x] `build/build.py` with `src.google_drive` hidden import
- [x] `PicPlotter.spec` updated for new repo path + google_drive module
- [x] `.gitignore` updated to track `build/build.py`
- [x] GitHub repo created (private): `rkinder9168/PicPlotter_web_claude`
- [x] GitHub Actions build workflow verified (Windows + macOS)
- [x] Removed Windows-incompatible `Zone.Identifier` file from tracking

---

## Testing Checklist

Before distribution, verify:

### Core (inherited)
- [ ] App launches without errors
- [ ] File selection dialog works
- [ ] JPG photos with GPS are detected correctly
- [ ] HEIC photos with GPS are detected correctly
- [ ] Photos without GPS show --- until manually placed
- [ ] Quality slider affects output file size
- [ ] Map editor opens when clicking "Open Map Editor"
- [ ] Marker drag updates positions
- [ ] Manual placement works for photos without GPS
- [ ] Group labels persist across editor sessions
- [ ] Rotation preview matches export output
- [ ] Offline HTML export opens without internet
- [ ] KMZ opens in Google Earth Pro

### Google Drive Import
- [ ] "Import from Drive" button toggles URL input panel
- [ ] Paste shared folder URL -> photos appear with thumbnails and GPS markers
- [ ] Web deploy -> HTML is small (no base64 photos), photos load from Drive URLs
- [ ] Local HTML export with Drive photos -> self-contained HTML with embedded photos
- [ ] KMZ export with Drive photos -> KMZ contains downloaded/processed images
- [ ] Mixed workflow: local + Drive photos both appear in editor
- [ ] Invalid folder URL -> clear error message
- [ ] Unshared folder -> "Access denied" error
- [ ] Missing API key -> "Please set your API key" error
- [ ] Drive API not enabled -> clear setup instructions in error

---

## Version History

### v3.0.0 (Current)
- Google Drive folder import with URL-referenced web deployments
- No new dependencies (stdlib urllib)
- Separate repo: `PicPlotter_web_claude`
- GitHub Actions CI for Windows and macOS installers

### v2.5.0
- Performance optimizations: 3x faster metadata extraction, parallel image processing
- Code cleanup: removed ~3,000 lines of dead code
- Centralized constants and utilities in config.py
- NumPy-vectorized marker colorization (10-50x faster)

### v2.4.0
- Manual placement for any photo (including non-GPS)
- Group labels in the map editor

### v2.2.0
- Single-window architecture with view switching

### v2.1.0
- Modern dark-themed UI with CustomTkinter

### v2.0.0
- Complete rebuild from v1.0
- KMZ-based architecture (no cloud dependencies)
- Single executable distribution

---

## Quick Commands

### Run from source (Windows)
```cmd
cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_web_claude
python -m src.main
```

### Build executable (Windows)
```cmd
cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_web_claude
python build/build.py
```

### CI Build
Go to https://github.com/rkinder9168/PicPlotter_web_claude/actions -> Build Installers -> Run workflow

### Verify syntax (WSL)
```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in __import__('glob').glob('src/*.py')]"
```
