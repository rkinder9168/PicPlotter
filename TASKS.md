# TASKS.md - Task Tracking and Status

**Related Docs**: [CLAUDE.md](./CLAUDE.md) | [PLANNING.md](./PLANNING.md)

---

## Project Status: Feature Complete — v4.0.0

All planned features implemented. Windows and macOS builds available via GitHub Actions.

**Current Notes**
- Single-window pywebview app with embedded tile-based editor view
- Google Drive folder import with URL-referenced web deployments
- Offline HTML export uses a stitched 2k snapshot (no API key required)
- Tile-based preview matches the export snapshot
- Manual placement for non-GPS photos and per-photo group labels in the editor
- Page mode: organize photos into named deliverable pages; multi-page interactive HTML export with per-page background, view, rotation, and legend
- Per-project Netlify URLs: each saved project keeps its own permanent site/URL; redeploys update the same link
- Full project state (placements, custom background, headings, page state, deploy URL) round-trips through the project JSON
- Create KMZ / Create Interactive Image auto-save the project first
- CI builds Windows `.exe` installer and macOS `.dmg` automatically on push to `main` (also available via manual dispatch)

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

### Phase 16: Per-Project Netlify URL + Full Project State Round-Trip (v4.0.0)
- [x] `src/netlify_deployer.py` — `_ensure_site()` reuses an existing `site_id` via GET (handles 404/410), creates a new site with a `picplotter-maps-<8hex>` suffix when none. Removed the destructive "delete then recreate" loop. `DeployResult` now carries `site_id`.
- [x] `src/config.py` — dropped global `get/set_netlify_site_id` + `NETLIFY_SITE_ID_FIELD`; `set_netlify_token("")` no longer wipes site IDs (they're per-project now).
- [x] `src/main.py` — `AppState` gains `current_project_name`, `netlify_site_id`, `netlify_deploy_url`; `_deploy_html_to_netlify()` reuses the active project's site and writes the result back to state + project JSON.
- [x] `src/main.py` — `_serialize_overrides_state(state)` extracted from `_apply_overrides`; embedded in `save_project` so the project JSON carries the full editor overrides payload (markers, custom_map_path, custom_markers, headings, autoplot, marker_size, groups + group_assignments + group_aliases, pages + page_assignments + per-page editor state, photo_aliases, photo_notes).
- [x] `src/main.py` — `_persist_active_project_overrides()` rewrites the active project's JSON on every `save_overrides` (editor's debounced save) and on deploy success.
- [x] `src/main.py` — `_reset_state_for_new_project()` wipes per-project fields (selected_files, gps_overrides, custom_marker_overrides, custom_map_path, headings, autoplot, aliases/notes) and calls `group_assignments.clear_all()` + `page_assignments.clear_all()`. Called from `clear_photos` and `load_project`.
- [x] `src/main.py` — `load_project` unconditionally replays saved data through `_apply_overrides` so group-mode top-level state is restored alongside per-page editor state.
- [x] `assets/app.html` — UI restructure: New Project button (`btn-white`) left, Save + Delete right; horizontal `.field-row` layout for Project Name / Proposal Link / Raw Photos Link / Client / Company / Address / Image Quality; "Saved Projects" → "Projects"; "Download Photos" → "Raw Photos Link"; default Image Quality 10%; "Optional" placeholders; deploy link panel under Save/Delete (`#project-deploy-link`).
- [x] `assets/app.html` — `ensureProjectSaved()` gates `openEditor` and `startKmzExport`; `clearForNewProject()` resets `editor.customMap`, `editor.pageStates`, `customImageEl.src`, and pending `editor.overrideTimer` so stale DOM/state can't bleed through.
- [x] End-to-end: per-project URL persists across redeploys + sessions; switching between projects keeps each project's background, placements, and deploy URL intact (group+page × tiles+custom).

### Phase 14: User-Configurable Branding (v3.2.0)
- [x] `src/config.py` — `get/set_user_logo_from_bytes` (PIL-validated, JPG/PNG only, normalized to PNG ≤ 512px long-edge at `~/.picplotter_auto/logo.png`), `clear_user_logo`, `get/set_company_info` with website normalization (`_normalize_website` auto-prepends `https://`)
- [x] `src/marker_utils.py` — `_load_base_image()` prefers user logo, both user logo and EverLine fallback go through `_normalize_to_square()` with `LOGO_CONTENT_RATIO` margin; `colorize_marker()` rewritten to draw a colored rectangular outline around the logo's alpha bbox (default group = black rectangle); `reset_colorizer()` for cache invalidation; NumPy import dropped
- [x] `src/html_map_generator.py` — dropped hardcoded `LOGO_FILENAME`; `_get_logo_image_src()` prefers user logo; new `company_*` kwargs and `_build_prepared_by_html()` helper; CSS for `#prepared-by` block; `.marker-number` repositioned to lower-right with white badge background; obsolete black-group `.marker-number` color rule removed
- [x] `src/main.py` — pywebview API: `get_branding`, `select_and_save_logo` (with inline `{ok, error}` returns for non-image / HEIC / corrupted uploads), `clear_logo`, `save_company_info`; threaded `**get_company_info()` into all four `HTMLMapGenerator(...)` call sites
- [x] `assets/app.html` — Branding section in Options → Settings: logo upload row with preview + reset, four company info inputs that auto-save on blur; CSS for marker badge in lower-right corner; obsolete `computeLabelOffset` and black-group green-text JS removed
- [x] Verified end-to-end: backwards compat (no branding configured), JPG/PNG/wide/tall/oversized uploads, invalid file errors, website normalization, logo center pixels preserved (no tinting), default + black + colored group rectangles

### Phase 15: Page Mode
- [x] `src/photo_pages.py` — new module with `PhotoPage`, `PageEditorState`, `PageAssignments`; Page 1 locked default; `add_page`, `remove_page` (reassigns photos to Page 1), `rename_page`, `assign_photo`, `prune_to_photos`, `auto_assign_unassigned`, `clear_all`
- [x] `src/main.py` — `AppState.assignment_mode` (`"group"` | `"page"`) and `page_assignments`; pywebview API: `set_assignment_mode`, `get_assignment_state`, `add_page`, `delete_page`, `rename_page`, `assign_photo_page`, `select_page_custom_map_image`; `_serialize_page_state()` and `_sync_page_assignments()` keep frontend state in sync; per-page editor state (map source, GPS/custom overrides, headings, views) loaded/saved with project memory and `map_overrides.json`
- [x] `src/marker_utils.py` — plain marker variant (no colored rectangle outline) for Page mode markers
- [x] `src/html_map_generator.py` — `generate_multi_page_html()` builds a single self-contained HTML with ordered `pages[]` payload (id, name, background, dimensions, photos, marker pixels, legend); deliverable JS swaps background, markers, lightbox scope, and legend on page change
- [x] `assets/app.html` — `Group | Page` segmented toggle replacing the static "Groups" heading; page list with add/rename/delete; neutral page-assignment dot in file list when in Page mode; editor sidebar page selector with Auto/Custom source toggle; mode-aware export/deploy paths
- [x] `tests/test_photo_pages.py`, `tests/test_page_backend_state.py`, `tests/test_html_multi_page_generator.py` — unit tests for assignment lifecycle, sync/prune behavior, and multi-page HTML generation
- [x] `docs/page-mode-feature-plan.md` — feature plan checked into the repo

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

### Page Mode (Phase 15)
- [ ] `Group | Page` toggle switches active mode without losing the inactive mode's data
- [ ] Page mode hides color swatches/picker and group-mode controls
- [ ] Add page → appears in page list; default name is "Page N"
- [ ] Rename page → name updates everywhere it's shown
- [ ] Delete non-default page → its photos move to Page 1; Page 1 cannot be deleted
- [ ] Assign photo to page → file list dot reflects the assigned page; reassignment moves the photo, never duplicates
- [ ] Editor page selector swaps the active page's background, view, rotation, and placements
- [ ] Page can use Auto satellite mode or Custom image mode independently of other pages
- [ ] Manual placement, custom calibration, and custom auto-plot all work per active page
- [ ] Multi-page HTML export produces a single file with page navigation, per-page background, and per-page legend
- [ ] Page mode markers use the user's logo with no colored rectangle outline
- [ ] Group mode export/deploy still uses the existing single-page generator path
- [ ] KMZ export still works in both modes (single-page, group/placement based)
- [ ] Saved project with Page mode reloads with all pages, assignments, and per-page editor state intact
- [ ] Legacy project saved before Page mode loads as Group mode with no pages defined

---

## Version History

### v4.0.0
- Per-project Netlify URLs: each saved project owns a permanent `site_id` + deploy URL stored in its JSON; redeploys update the same site so client links don't break when other projects are deployed
- `NetlifyDeployer` no longer deletes sites — it reuses the project's existing one (or creates a fresh one when missing)
- Full project state now round-trips through the project JSON: photo placements, custom background image, headings, group + page assignments and per-page editor state, aliases/notes, Netlify URL
- `_persist_active_project_overrides()` syncs the project JSON on every debounced editor save and on deploy, so anything picked inside the editor (e.g. custom background) lands in the project file
- `_reset_state_for_new_project()` clears all per-project fields on New Project / Load Project so nothing leaks between projects
- Create KMZ and Create Interactive Image auto-save the active project first (Project Name required)
- UI polish: New Project button (white, left) + Save/Delete (right) above the Projects dropdown; horizontal label+input rows for the main fields; default Image Quality 10%; "Optional" placeholders; "Saved Projects" → "Projects", "Download Photos" → "Raw Photos Link"; deployed URL surfaced under Save/Delete on the home page

### Page Mode (released with v4.0.0)
- New `assignment_mode: "group" | "page"` state with a Group/Page toggle in the UI
- Photos can be organized into named pages (Page 1 locked as default; deleting a page reassigns its photos to Page 1)
- Each page owns its own editor state: map source (Auto satellite or Custom image), GPS overrides, custom marker overrides, headings, and tile/custom view
- Multi-page interactive HTML deliverable with page navigation and per-page legend
- Page mode markers use the user's logo without the colored rectangle outline
- KMZ export remains group/placement based (single-page)
- New `src/photo_pages.py` module and `tests/` directory with unit coverage for page assignments, backend state sync, and multi-page HTML generation

### v3.2.0
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
