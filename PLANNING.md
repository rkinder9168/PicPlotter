# PLANNING.md - Architecture and Design Decisions

**Related Docs**: [CLAUDE.md](./CLAUDE.md) | [TASKS.md](./TASKS.md)

---

## Problem Statement

### PicPlotter v1.0 Issues

The original PicPlotter v1.0 required:
1. Google Cloud Console account setup
2. OAuth 2.0 credential configuration
3. Google Drive API enablement
4. Two separate executables (Setup + Main app)
5. ~15 minute setup process for non-technical users
6. Active internet connection for photo hosting

This complexity made the app impractical for general public distribution.

### Requirements for v2.0
- Zero setup - works immediately after download
- Single executable file
- No cloud dependencies
- Works completely offline
- Output files are self-contained and shareable

### v3.0 - Google Drive URL References
- Import photos from shared Google Drive folders
- Web deployments reference photos by URL (no download/re-upload)
- Local HTML and KMZ exports remain self-contained (download photos automatically)
- No new Python dependencies (uses stdlib `urllib`)

### v4.0 - Per-Project Netlify URL + Project State Round-Trip
- Each saved project owns a permanent Netlify `site_id` + deploy URL; redeploys update the same site so client links never expire when other projects are deployed
- `NetlifyDeployer._ensure_site()` reuses the project's existing site (GET check) or creates a new one with a unique `picplotter-maps-<8hex>` suffix — sites are never deleted (the old "delete then recreate" loop was what nuked other projects' URLs)
- Saved project JSON now carries the full editor overrides payload (`custom_map_path`, gps + custom-marker placements, headings, autoplot, marker size, groups, page assignments + per-page editor state, aliases/notes), so reloading restores the background image and placements — not just the form fields
- `_persist_active_project_overrides()` rewrites the project JSON on every debounced editor save and on deploy, so custom backgrounds picked *inside* the editor land in the file
- `_reset_state_for_new_project()` wipes all per-project state on New Project and on Load Project so nothing leaks across projects (custom background, per-page editor state, headings, autoplot, aliases/notes, groups, pages)
- Auto-save flow: Create KMZ and Create Interactive Image require a Project Name and save the project before proceeding
- UI polish: New Project button (white) left of Save/Delete (right), horizontal label+input rows for Project Name / Proposal Link / Raw Photos Link / Client / Company / Address / Image Quality, default Image Quality 10%, "Optional" placeholders replace redundant hint divs, "Saved Projects" → "Projects" and "Download Photos" → "Raw Photos Link", deployed URL surfaced under Save/Delete on the main page

### v4.2 - Media Formats + Display Options
- Import Media accepts PNG in addition to JPG/HEIC; `.png` added once to `is_supported_format`/`get_supported_extensions` (exif_extractor) so it propagates to the file dialog, `is_supported_media`, and validation. PNGs without GPS follow the existing manual-placement path; RGBA is composited onto white during JPEG compression
- Two per-project boolean display options, `hide_markers` and `hide_sidebar`, modeled on the existing `marker_size` flow (persisted in `map_overrides.json` + project JSON, round-tripped via `_serialize_overrides_state`/`_apply_overrides`, seeded into the editor via `get_editor_state`/`_build_html`)
- Invisible markers hide the logo + number badge on the deployed page but keep each marker a clickable hotspot (the `.marker` div stays sized in the DOM, so existing click handlers still open the lightbox); the editor renders a dashed-circle ghost with the number so placement stays visible. Implemented purely with a `markers-hidden` body class + CSS in both HTML templates — no markup change
- Hide-sidebar collapses the `#layout` grid (`no-sidebar` body class). It is only meaningful when there is no page navigation to lose, so the multi-page generator emits `no-sidebar` only when `page_count <= 1`, and the editor disables the checkbox when a project has 2+ pages

### v4.1 - Video Media
- Photos and short videos (`.mp4/.mov/.m4v/.webm`) share the import/placement pipeline; videos play in the web (Netlify) deliverable (Drive via embed iframe, local uploaded as `/media/...` assets) while single-file HTML and KMZ strip video with a warning
- GPS parsed from MP4/MOV ISO-BMFF containers in a pure-stdlib `src/video_metadata.py` (no ffmpeg); local files reliable, Drive best-effort → manual placement
- Format classification centralized in `is_supported_media` / `get_supported_media_extensions` (photo helpers + video helpers), keeping one source of truth for the file dialog and validation

### v3.3 - Page Mode
- Photos can be organized into named deliverable pages instead of (or alongside) colored groups
- New `assignment_mode: "group" | "page"` toggle in the UI; inactive mode's data is preserved, only the active mode drives the editor and exports
- Each page owns its own editor state: map source (`tiles` or `custom`), GPS overrides, custom image + calibration, headings, and tile/custom view
- Page 1 is the locked default; deleting any other page reassigns its photos to Page 1
- Page mode markers use the user's logo with no colored outline (group identity doesn't apply)
- New multi-page HTML deliverable with page navigation, per-page background, and a legend scoped to the active page
- KMZ export remains group/placement based and is not multi-page
- New `src/photo_pages.py` module owns `PhotoPage`, `PageEditorState`, and `PageAssignments`

### v3.2 - User-Configurable Branding
- Replace hardcoded branding with global, user-configurable assets
- Logo upload (JPG/PNG, normalized to ≤ 512px PNG) becomes the photo marker base AND the HTML sidebar header logo
- Group identity moves from pixel-tinting the logo to drawing a colored rectangular outline around it — preserves brand colors while keeping groups visually distinct
- Marker numbers move to a small white badge in the lower-right corner so they remain readable against any logo
- New "Prepared by" block in HTML deliverables (company name, address, phone, optional website) sits alongside the existing client info; website strings are normalized (auto-prepend `https://`, render plain text when no `.`)
- Settings stored globally at `~/.picplotter_auto/logo.png` and in `~/.picplotter_auto/config.json`; bundled generic pin (`assets/marker_pin.png`) is the marker fallback; no default header logo

---

## Solution: Hybrid Architecture

### KMZ + HTML Exports (Self-Contained)
KMZ (Keyhole Markup Zip) and local HTML exports embed all images directly. For Drive-sourced photos, the app downloads them automatically before embedding.

### Web Deploy (URL-Referenced)
Netlify deployments reference Google Drive photos by URL, eliminating the 3-hop data flow (Drive -> local download -> app processing -> Netlify upload). The HTML contains `<img src="https://drive.google.com/thumbnail?id=...">` instead of base64-encoded data.

### Google Drive Integration
- **API**: Google Drive API v3 via `urllib` (no `google-api-python-client` dependency)
- **Auth**: Uses the same Google Maps API key (user must enable Drive API on their Cloud project)
- **Virtual paths**: Drive photos use `gdrive://{file_id}/{filename}` as keys in state dicts
- **Metadata**: Tries Drive API `imageMediaMetadata` first, falls back to partial download (~128KB) + Pillow EXIF extraction

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Cross-platform, rich ecosystem |
| GUI | pywebview (single window) | Modern UI with embedded Google tile editor |
| Image Processing | Pillow | Industry standard, handles EXIF |
| HEIC Support | pillow-heif | Apple photo format support |
| Drive API | stdlib urllib | No new dependencies |
| XML Generation | ElementTree | Built into Python |
| Build | PyInstaller | Single-file executable |
| CI/CD | GitHub Actions | Automated Windows/macOS builds |
| Map Editor | Google tile renderer | Tile-based map with rotation and marker edits |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    main.py (pywebview UI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ File Select  │  │  Drive Import│  │    Progress/Status     │ │
│  │   Dialog     │  │  URL Input   │  │       Display          │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
          ┌─────────────────┐  ┌─────────────────┐
          │  Local Photos   │  │  Drive Photos   │
          │ (file on disk)  │  │ (virtual path)  │
          └────────┬────────┘  └────────┬────────┘
                   │                    │
                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Processing Pipeline                          │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ exif_extractor  │───▶│ image_processor │───▶│   export    │ │
│  │                 │    │                 │    │             │ │
│  │ - Read EXIF     │    │ - HEIC→JPG      │    │ - KMZ       │ │
│  │ - Extract GPS   │    │ - Fix rotation  │    │ - HTML      │ │
│  │ - From bytes    │    │ - Resize        │    │ - Netlify   │ │
│  └─────────────────┘    │ - From bytes    │    └─────────────┘ │
│                         └─────────────────┘                     │
│  ┌─────────────────┐                                            │
│  │ google_drive    │  (Drive photos only)                       │
│  │ - List folder   │                                            │
│  │ - Get URLs      │  Web deploy: image_url (no download)       │
│  │ - Fetch bytes   │  Local export: fetch + process_image_bytes │
│  └─────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Google Drive Data Flow

### Web Deploy (fast path - no photo bytes transferred)
```
Drive folder URL
  → list_folder_images() via Drive API
  → extract metadata (GPS) from imageMediaMetadata or partial download
  → build photo dicts with image_url = drive.google.com/thumbnail?id=...
  → generate HTML referencing URLs
  → deploy small HTML to Netlify
```

### Local/KMZ Export (self-contained path)
```
Drive folder URL
  → list_folder_images() via Drive API
  → extract metadata (GPS)
  → fetch_image_bytes() for each photo
  → process_image_bytes() (resize, compress)
  → embed in HTML/KMZ as base64/binary
```

---

## Build Configuration

### CI (GitHub Actions)
- Triggered automatically on push to `main`; also available via `workflow_dispatch`
- Concurrency group `build-installers` cancels any in-flight run when a new push lands
- Reads version from `src/__init__.py`
- Creates GitHub Release with tag `v{version}` bound to the build SHA, then a final `publish` job promotes it to draft=false + latest after both installer jobs upload
- Windows: PyInstaller `--onefile` + Inno Setup installer
- macOS: PyInstaller `--onedir` + DMG

### Local Build (Windows)
```cmd
cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_web_claude
python build/build.py
```

### PyInstaller Hidden Imports
All `src.*` modules must be listed as hidden imports, including `src.google_drive`.

---

## Error Handling Strategy

| Scenario | Handling |
|----------|----------|
| No GPS data | Show in list, skip from map, allow manual placement |
| Unsupported format | Skip, add to error list |
| Drive API not enabled | Clear error message with setup instructions |
| Folder not shared | "Access denied" with sharing instructions |
| Invalid API key | "Invalid API key" message |
| Drive photo download fails | Skip photo, add to error list |
| Partial EXIF extraction fails | Still add photo (without GPS) |
| All photos skipped | Show error, don't create empty export |

---

## Project Memory

Projects are saved as individual JSON files in `~/.picplotter_auto/projects/{name}.json`. Each project stores the full editor state so a reload restores exactly what the user left, including the deployed link.

- Form fields: project name, proposal link, raw photos link, client name, company, address
- Image quality setting, output folder, Drive folder URL, `selected_files`, `drive_sources`
- Full editor overrides (via `_serialize_overrides_state` — the same payload `_apply_overrides` writes to `map_overrides.json`): `assignment_mode`, marker_size, heading, custom_heading, markers (gps overrides), custom_map_path, custom_markers (pixel placements), custom_autoplot_enabled, photo_aliases, groups, group_assignments, group_aliases, pages (with per-page editor state), page_assignments, photo_notes
- Netlify per-project state: `netlify_site_id`, `netlify_deploy_url`

`_persist_active_project_overrides()` rewrites the project JSON every time the editor's debounced `save_overrides` fires, so the custom background image and placements chosen *inside* the editor land in the project file (not just `map_overrides.json`). The same helper runs after a successful deploy. `load_project` first calls `_reset_state_for_new_project()` (clearing per-page editor state, `custom_map_path`, etc.) and then replays the saved data through `_apply_overrides`, so nothing leaks from the previous project.

The UI surfaces a New Project button (left), a Projects dropdown that loads on selection, Save and Delete buttons (right), and a "Deployed: <link>" line that appears under the buttons whenever the loaded project has a stored Netlify URL. Create KMZ and Create Interactive Image auto-save the project first (requires a Project Name).

---

## Branding (Global)

Branding is intentionally global rather than per-project — the typical user is one company shipping every deliverable under the same identity, so re-entering it per project would be churn.

- Logo file lives at `~/.picplotter_auto/logo.png` (always normalized to PNG on save). Lookup precedence in `MarkerColorizer._load_base_image()` and `HTMLMapGenerator._get_logo_image_src()`: user file → bundled marker fallback (`assets/marker_pin.png`); header logo has no fallback.
- Company info (name, address, phone, website) lives in the existing `~/.picplotter_auto/config.json`.
- After a logo upload, `reset_colorizer()` invalidates the in-memory marker cache so the next editor session and next export pick up the new logo.
- Markers render as `_normalize_to_square(logo)` + colored rectangle outline drawn around the logo's alpha bbox; logo pixels are never modified, only framed.

---

## Page Mode Architecture

Page mode is implemented in `src/photo_pages.py` and integrated through `src/main.py` and `src/html_map_generator.py`:

- `PhotoPage` — id, display name, assigned photo paths, per-page `PageEditorState`, and a `locked` flag (true only for Page 1)
- `PageEditorState` — `map_source` (`tiles` or `custom`), `gps_overrides`, `custom_map_path`, `custom_marker_overrides`, `custom_autoplot_enabled`, `heading`, `custom_heading`, `tile_view`, `custom_view`. Each page is independently calibratable and rotatable.
- `PageAssignments` — owns the page dict, with `assign_photo`, `unassign_photo`, `add_page`, `remove_page` (reassigns to Page 1), `rename_page`, `prune_to_photos` (removes stale paths from pages and editor state), and `auto_assign_unassigned` (Page 1 catches everything by default).
- `AppState.assignment_mode` (`"group"` | `"page"`) selects which mode drives the editor and exports. Group mode data is untouched while Page mode is active and vice versa.
- `HTMLMapGenerator.generate_multi_page_html()` builds a single self-contained HTML containing every page's background, photos, marker pixels, and legend; the deliverable's JS swaps backgrounds, marker overlays, lightbox scope, and legend rows on page change. The deliverable is mobile-responsive (slide-out sidebar, touch pan/pinch, safe-area-aware lightbox).
- `marker_utils.get_plain_marker_bytes()` (called from the multi-page generator) returns the user's logo without the colored rectangle outline — Page mode has no per-group color.
- Page state persists in `map_overrides.json` and saved projects with backward-compatible defaults so older projects load as Group mode with no pages.

---

## Future Considerations

### Potential Enhancements (Not Currently Planned)
- Drag-and-drop file support
- Batch folder processing
- Export to other formats (GeoJSON, GPX)
- Photo grouping/clustering for dense areas
- Multi-page KMZ export (currently single-page, group/placement based)
