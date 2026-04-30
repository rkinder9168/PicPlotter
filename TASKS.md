# TASKS.md - Task Tracking and Status

**Related Docs**: [CLAUDE.md](./CLAUDE.md) | [PLANNING.md](./PLANNING.md)

---

## Project Status: v3.2.0 - Feature Complete

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

### Phase 13: Project Memory
- [x] `src/config.py` — `list_projects()`, `save_project()`, `load_project()`, `delete_project()` storing JSON in `~/.picplotter_auto/projects/`
- [x] `src/main.py` — `AppApi` methods: `get_projects`, `save_project`, `load_project`, `delete_project`
- [x] `src/main.py` — Initial state includes project list for dropdown population
- [x] `assets/app.html` — "Saved Projects" dropdown with Save/Load/Delete buttons
- [x] `assets/app.html` — JS functions to populate dropdown, save/load/delete projects
- [x] Saves: project name, proposal link, client name, company, address, quality, output folder, Drive folder URL

### Phase 14: User-Configurable Branding (v3.2.0)
- [x] `src/config.py` — `get/set_user_logo_from_bytes` (PIL-validated, JPG/PNG only, normalized to PNG ≤ 512px long-edge at `~/.picplotter_auto/logo.png`), `clear_user_logo`, `get/set_company_info` with website normalization (`_normalize_website` auto-prepends `https://`)
- [x] `src/marker_utils.py` — `_load_base_image()` prefers user logo, both user logo and EverLine fallback go through `_normalize_to_square()` with `LOGO_CONTENT_RATIO` margin; `colorize_marker()` rewritten to draw a colored rectangular outline around the logo's alpha bbox (default group = black rectangle); `reset_colorizer()` for cache invalidation; NumPy import dropped
- [x] `src/html_map_generator.py` — dropped hardcoded `LOGO_FILENAME`; `_get_logo_image_src()` prefers user logo; new `company_*` kwargs and `_build_prepared_by_html()` helper; CSS for `#prepared-by` block; `.marker-number` repositioned to lower-right with white badge background; obsolete black-group `.marker-number` color rule removed
- [x] `src/main.py` — pywebview API: `get_branding`, `select_and_save_logo` (with inline `{ok, error}` returns for non-image / HEIC / corrupted uploads), `clear_logo`, `save_company_info`; threaded `**get_company_info()` into all four `HTMLMapGenerator(...)` call sites
- [x] `assets/app.html` — Branding section in Options → Settings: logo upload row with preview + reset, four company info inputs that auto-save on blur; CSS for marker badge in lower-right corner; obsolete `computeLabelOffset` and black-group green-text JS removed
- [x] Verified end-to-end: backwards compat (no branding configured), JPG/PNG/wide/tall/oversized uploads, invalid file errors, website normalization, logo center pixels preserved (no tinting), default + black + colored group rectangles

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

### Branding (Phase 14)
- [ ] Default state with no logo uploaded -> EverLine swoosh + horizontal logo still appear; no "Prepared by" block in exports
- [ ] PNG upload (square, wide, tall) -> logo previews instantly; markers in editor and HTML use the new logo with colored rectangle outline
- [ ] JPG upload -> converted to PNG, white-background logos still readable
- [ ] Oversized upload (> 512px) -> auto-downscaled to ≤ 512px long-edge
- [ ] Invalid uploads (HEIC, .txt, corrupted) -> inline "Logo must be JPG or PNG" error, no crash
- [ ] Company info (all four fields) -> "Prepared by" block renders in HTML with clickable website link
- [ ] Company info with no logo uploaded -> "Prepared by" block still renders (text only)
- [ ] Website normalization: blank, `example.com`, `https://x.com`, `http://x.com`, `not a url`
- [ ] Reset to Default -> EverLine assets return; `~/.picplotter_auto/logo.png` deleted
- [ ] Persistence: close + reopen app, branding reloads
- [ ] KMZ markers unchanged (still red dot - explicit out-of-scope)
- [ ] Marker number badges visible against any logo background

---

## Version History

### v3.2.0 (Current)
- User-configurable branding: upload custom logo (JPG/PNG) and company contact info; settings stored globally at `~/.picplotter_auto/logo.png` and `config.json`
- Markers re-engineered: logo pixels are preserved unchanged; group identity comes from a colored rectangular outline drawn around the logo (default group = black rectangle)
- Marker numbers moved to a small white badge in the lower-right corner so they remain readable against any logo
- New "Prepared by" block in HTML deliverables with company name, address, phone, and clickable website link
- NumPy dependency no longer used by `src/*` (kept in requirements.txt as a transitive safety net)

### v3.1.0
- Project memory: save/load project settings (name, client, address, etc.)
- Projects stored as JSON in `~/.picplotter_auto/projects/`

### v3.0.0
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
