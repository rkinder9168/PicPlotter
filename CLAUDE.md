# CLAUDE.md - Project Context

## Quick Reference

**Project**: PicPlotter Auto (Web/Drive edition)
**Repo**: `PicPlotter_web_claude`
**Purpose**: Auto-plot geotagged photos (and videos) on Google satellite imagery and export KMZ/HTML. Supports Google Drive folder import with URL-referenced web deployments. Videos are placed like photos and play in the web (Netlify) deliverable.
**Status**: Feature complete, v4.1.0 — Photo + video media (videos play in web deploy); Page mode + per-project Netlify URL persistence
**Related Docs**: [PLANNING.md](./PLANNING.md) | [TASKS.md](./TASKS.md) | [docs/page-mode-feature-plan.md](./docs/page-mode-feature-plan.md)

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
4. **CI Build** - GitHub Actions `Build Installers` workflow runs automatically on every push to `main` (and on manual dispatch); creates Windows `.exe` installer and macOS `.dmg`, attached to a GitHub Release.

---

## Project Overview

PicPlotter Auto uses a tile-based Google satellite editor to adjust markers and rotation, then exports a single-file offline HTML deliverable (2k snapshot). Marker adjustments apply to KMZ exports.

### Key Value Proposition
- **Automatic map placement** - no manual calibration clicks
- **Manual corrections** - drag markers for fine-tuning
- **Google Drive import** - load photos from shared folders; web deploys use URL references (no download/re-upload)
- **Photos + videos** - videos (`.mp4/.mov/.m4v/.webm`) import from local disk and Drive, place on the map like photos (logo markers), and **play in the web (Netlify) deliverable** — Drive videos via Drive's embed player, local videos uploaded as Netlify assets. Single-file HTML and KMZ exclude video (with a warning). GPS is parsed from MP4/MOV containers (local reliable; Drive best-effort → manual placement)
- **KMZ and HTML exports** - deliver to Google Earth Pro or clients
- **Deploy to Web** - Netlify deployment; each saved project owns a permanent Netlify site_id + URL stored in its JSON, so redeploys update the same site instead of clobbering other projects' links
- **Project memory** - save/load full per-project state: form fields, photo lists/drive sources, every editor override (`custom_map_path`, gps + custom marker placements, headings, autoplot, marker size, groups, page assignments + per-page editor state), and the Netlify site/URL. `_persist_active_project_overrides()` syncs the project JSON on every debounced editor save and on deploy.
- **Custom branding** - global logo upload (JPG/PNG) + company info ("Prepared by" block in HTML deliverables); logo serves as the photo marker base, group identity comes from a colored rectangular outline
- **Page mode** - alternative to colored groups: organize photos into named pages, each with its own background/view/rotation/placements; exports a multi-page interactive HTML with page navigation and per-page legend
- **Single executable** - one .exe to distribute

---

## Project Structure

```
/home/rkinder9168/projects/PicPlotter_web_claude/
├── src/
│   ├── __init__.py             # Package marker + version
│   ├── main.py                 # Entry point + single-window pywebview UI
│   ├── config.py               # API key config, constants, project management
│   ├── exif_extractor.py       # GPS coordinate extraction from EXIF (photos)
│   ├── video_metadata.py       # MP4/MOV GPS parsing + photo/video classification helpers
│   ├── image_processor.py      # HEIC conversion, compression, EXIF orientation
│   ├── kmz_generator.py        # KML/KMZ generation with embedded images
│   ├── html_map_generator.py   # HTML map export with interactive markers
│   ├── google_drive.py         # Google Drive API client (folder listing, URLs, download)
│   ├── marker_utils.py         # Logo normalization + colored rectangle outline (PIL); plain marker variant for Page mode
│   ├── photo_groups.py         # Photo group management (Group mode)
│   ├── photo_pages.py          # Photo page assignments + per-page editor state (Page mode)
│   ├── coordinate_transform.py # PixelPoint and AffineTransform helpers
│   ├── netlify_deployer.py     # Netlify deployment for web sharing
│   └── utils.py                # File/folder utilities
├── tests/                      # Unit tests (photo_pages, multi-page HTML, backend page state)
├── docs/
│   └── page-mode-feature-plan.md
├── assets/
│   ├── marker_outlined_transparent.png  # Bundled fallback marker base
│   ├── everline-horizontal-logo.jpg     # Bundled fallback header logo
│   └── app.html
├── build/
│   └── build.py                # Cross-platform PyInstaller build script
├── packaging/
│   ├── windows/PicPlotterAuto.iss  # Inno Setup installer script
│   └── macos/build_dmg.sh          # macOS DMG builder
├── .github/workflows/build.yml # CI: build installers on push to main / manual dispatch
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
- `import_from_drive()` - imports photos/videos from shared Google Drive folders
- Handles KMZ and HTML export using saved marker overrides
- Web deploy uses Drive image URLs (no download) when all photos are from Drive
- Parallel photo processing with ThreadPoolExecutor
- **Video support**: `_get_local_media_metadata()` dispatches photo (EXIF) vs video (MP4/MOV) metadata; `select_photos`/`load_project` accept media via `is_supported_media`/`get_supported_media_extensions`; `_get_photo_preview_uri()` uses the Drive thumbnail for Drive videos and `_VIDEO_PLACEHOLDER_URI` (inline ▶ SVG) for local videos; `_build_photo_list` sets `is_video`. `_video_export_dict()` builds video export dicts (Drive→`embed`+`video_url` preview iframe URL+`poster`; local→`local_video_path`+deferred `video_url`). `_collect_video_assets()` resolves local-video `media/<name>` URLs and returns bytes for `_deploy_html_to_netlify(..., extra_files=...)`. `_strip_video_markers()` drops videos from local HTML (`export_html`, returns a `warning`) and KMZ (`start_kmz_export`, reports `video_skipped`)
- `AppState.assignment_mode` (`"group"` | `"page"`) and `page_assignments`; pywebview API for Page mode: `set_assignment_mode`, `get_assignment_state`, `add_page`, `delete_page`, `rename_page`, `assign_photo_page`, `select_page_custom_map_image`
- `_serialize_page_state()` and `_sync_page_assignments()` keep frontend state in sync; per-page editor state persists in `map_overrides.json` and saved projects with backward-compatible defaults
- `_serialize_overrides_state(state)` returns the single canonical overrides payload (markers, custom_markers, custom_map_path, headings, autoplot, marker_size, groups, group_assignments, group_aliases, pages, page_assignments, photo_aliases, photo_notes). Used both by `_apply_overrides` to write `map_overrides.json` and by `save_project` to embed the full editor state in the project JSON.
- `_persist_active_project_overrides()` re-writes the active project's JSON whenever `save_overrides` runs (debounced from the editor) and after a successful deploy. No-op when no saved project is loaded.
- `_reset_state_for_new_project()` wipes every per-project field on `clear_photos` / `load_project` so a fresh project never inherits the previous one's custom background, placements, or per-page editor state.
- Per-project Netlify state lives on `AppState.current_project_name`, `netlify_site_id`, `netlify_deploy_url`. `_deploy_html_to_netlify()` reuses the project's existing site (validated via GET) or creates a new one with a unique suffix; never deletes sites. `set_netlify_token("")` no longer clears project URLs.

### `src/google_drive.py`
- Google Drive API v3 client using stdlib `urllib` (no extra dependencies)
- `parse_drive_folder_url()` - extracts folder ID from sharing URLs
- `list_folder_images()` - lists images with pagination
- `get_image_url()` / `get_thumbnail_url()` - public CDN URLs for shared files (the thumbnail doubles as a video poster — Drive auto-generates video thumbnails)
- `get_video_embed_url()` - Drive `/file/d/<id>/preview` embeddable player URL for shared videos
- `list_folder_images()` query (`_MEDIA_MIME_QUERY`) includes video MIME types (`video/mp4`, `video/quicktime`, `video/x-m4v`, `video/webm`)
- `fetch_image_bytes()` - full/partial file download for local exports
- `extract_metadata_from_drive()` - EXIF extraction from partial download

### `src/config.py`
- Saves/loads Google API keys and Netlify tokens from `~/.picplotter_auto/config.json`. The global `netlify_site_id` field is gone — sites live per-project.
- Project management: `list_projects()`, `save_project()`, `load_project()`, `delete_project()` — stores projects as JSON in `~/.picplotter_auto/projects/`. Each project JSON carries the full editor state (via `_serialize_overrides_state`) plus `netlify_site_id` and `netlify_deploy_url`.
- Branding (global, not per-project): `get/set_user_logo*` (PIL-validated, normalized to PNG ≤ 512px long-edge at `~/.picplotter_auto/logo.png`), `get/set_company_info` with website normalization
- Environment variable fallback (`GOOGLE_MAPS_API_KEY`)
- Centralized constants (TILE_SIZE, EXPORT_MAX_DIM, etc.)
- Shared `get_asset_path()` for PyInstaller compatibility

### `src/netlify_deployer.py`
- `NetlifyDeployer(token, site_id)` — `_ensure_site()` GETs the supplied site_id and reuses it if it still exists; on 404/410 (or when no site_id was supplied) creates a new site with a `picplotter-maps-<8hex>` unique name. Never deletes sites — that would break live client links.
- `deploy(html, name, extra_files=None)` / `_deploy_file()` deploy via the file-digest API; `extra_files` (a `path -> bytes` map) ships local video assets (`/media/<name>`) alongside `index.html`.
- `DeployResult` carries `site_id` back to the caller so the project JSON can be updated.
- `verify_token()` confirms a personal access token works.

### `src/exif_extractor.py`
- Extracts GPS, timestamp, camera info from EXIF in a single file open
- `get_image_metadata_from_bytes()` for in-memory EXIF extraction (Drive photos)
- Handles JPG and HEIC formats

### `src/video_metadata.py`
- Pure-stdlib MP4/MOV (ISO-BMFF) parsing — no extra dependency. Reuses `GPSCoordinates`/`ImageMetadata` from `exif_extractor`.
- Classification helpers: `is_video_format`, `get_video_extensions`, `video_mime_for`, plus combined `is_supported_media` / `get_supported_media_extensions` (one-way import from `exif_extractor`)
- `extract_video_gps(bytes)` walks boxes to the `moov` payload and reads GPS from the `©xyz` ISO-6709 atom (Android/iPhone), falling back to scanning for the QuickTime `com.apple.quicktime.location.ISO6709` string. `parse_iso6709()` handles decimal-degree strings.
- `extract_video_metadata(path)` reads only box headers + the `moov` payload (handles `moov`-at-end without loading the whole file) → GPS + best-effort `mvhd` timestamp; `extract_video_metadata_from_bytes()` for Drive partials (best-effort)

### `src/html_map_generator.py`
- Generates interactive HTML maps with aerial background and photo markers
- Supports both base64-embedded photos (`image_data`) and URL-referenced photos (`image_url`)
- **Video lightbox**: photo dicts flagged `is_video` carry `video_url` (+`embed`/`poster`). Both the single-page and multi-page lightboxes include a hidden `<video>` and `<iframe>`; `applyLightboxMedia()` shows the iframe for Drive embeds, the `<video>` for local `media/...` assets, or the `<img>` for photos, and `resetLightboxMedia()` stops playback on close/navigate. The per-photo payload carries `isVideo`/`embed`/`poster`
- Renders the user's logo in the sidebar header and an optional "Prepared by" block (`company_name`, `company_address`, `company_phone`, `company_website`) alongside the existing client info
- Marker numbers render as a small white badge in the lower-right corner of each marker so they remain readable against any logo
- `generate_multi_page_html()` builds a single self-contained multi-page deliverable for Page mode: ordered `pages[]` payload (id, name, background, dimensions, photos, marker pixels, legend); deliverable JS swaps background, markers, lightbox scope, and legend on page change. The deliverable is mobile-responsive — slide-out sidebar with scrim under 900px, pinch-to-zoom + one-finger pan via touch handlers, `env(safe-area-inset-*)` padding, and a `visualViewport` listener that keeps the lightbox usable as iOS Safari's URL bar collapses

### `src/marker_utils.py`
- Loads the marker base image — prefers the user-uploaded logo, falls back to the bundled `marker_outlined_transparent.png`
- `_normalize_to_square()` centers the logo on a transparent square canvas with margin (controlled by `LOGO_CONTENT_RATIO`) so the group rectangle has room to draw
- `colorize_marker()` draws a colored rectangular outline around the logo's alpha bbox — group identity comes from the rectangle color, not from tinting the logo. Default group uses a black rectangle.
- `MarkerColorizer` caches colored variants; `reset_colorizer()` invalidates the cache after a logo change
- `get_plain_marker_bytes()` returns the user's logo without the colored rectangle outline — used by the multi-page generator since Page mode has no per-group color

### `src/photo_pages.py`
- `PhotoPage` — id, display name, assigned photo paths, per-page `PageEditorState`, and a `locked` flag (true only for Page 1)
- `PageEditorState` — `map_source` (`tiles` or `custom`), `gps_overrides`, `custom_map_path`, `custom_marker_overrides`, `custom_autoplot_enabled`, `heading`, `custom_heading`, `tile_view`, `custom_view`. Each page is independently calibratable and rotatable.
- `PageAssignments` — owns the page dict; `assign_photo`, `unassign_photo`, `add_page`, `remove_page` (reassigns photos to Page 1), `rename_page`, `prune_to_photos`, `auto_assign_unassigned`, `clear_all`. Page 1 is the locked default and cannot be deleted.

---

## Dependencies

```
pillow>=10.0.0       # Image processing (and PIL.ImageDraw for marker outlines)
pillow-heif>=0.16.0  # HEIC/HEIF support
numpy>=1.20.0        # Listed in requirements.txt; not currently imported by src/* — kept as a transitive safety net for Pillow / PyInstaller
pywebview>=4.0       # Embedded map editor
pyinstaller>=6.0     # Executable creation (build only)
```

No additional dependencies for Google Drive support (uses stdlib `urllib`) or for video support (MP4/MOV GPS parsing is pure stdlib in `video_metadata.py`; no ffmpeg — local-video posters use an inline ▶ placeholder, Drive videos use Drive's auto thumbnail).

---

## WSL vs Windows

- **Development**: WSL (`/home/rkinder9168/projects/PicPlotter_web_claude/`)
- **Testing/Building**: Windows reads WSL files directly via `\\wsl$\Ubuntu\...`
- **CI**: GitHub Actions builds on `windows-latest` and `macos-latest`
