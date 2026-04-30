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

### v3.2 - User-Configurable Branding
- Replace hardcoded EverLine branding with global, user-configurable assets
- Logo upload (JPG/PNG, normalized to ≤ 512px PNG) becomes the photo marker base AND the HTML sidebar header logo
- Group identity moves from pixel-tinting the logo to drawing a colored rectangular outline around it — preserves brand colors while keeping groups visually distinct
- Marker numbers move to a small white badge in the lower-right corner so they remain readable against any logo
- New "Prepared by" block in HTML deliverables (company name, address, phone, optional website) sits alongside the existing client info; website strings are normalized (auto-prepend `https://`, render plain text when no `.`)
- Settings stored globally at `~/.picplotter_auto/logo.png` and in `~/.picplotter_auto/config.json`; bundled EverLine assets remain as fallback

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
- Triggered manually via `workflow_dispatch`
- Reads version from `src/__init__.py`
- Creates GitHub Release with tag `v{version}`
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

Projects are saved as individual JSON files in `~/.picplotter_auto/projects/{name}.json`. Each project stores:
- Project name, proposal link, client name, company, address
- Image quality setting, output folder, Drive folder URL

The UI provides a dropdown selector with Save/Load/Delete controls above the project fields. The project list is populated from the initial state on launch and updated dynamically after save/delete operations.

---

## Branding (Global)

Branding is intentionally global rather than per-project — the typical user is one company shipping every deliverable under the same identity, so re-entering it per project would be churn.

- Logo file lives at `~/.picplotter_auto/logo.png` (always normalized to PNG on save). Lookup precedence in `MarkerColorizer._load_base_image()` and `HTMLMapGenerator._get_logo_image_src()`: user file → bundled fallback (`assets/marker_outlined_transparent.png`, `assets/everline-horizontal-logo.jpg`).
- Company info (name, address, phone, website) lives in the existing `~/.picplotter_auto/config.json`.
- After a logo upload, `reset_colorizer()` invalidates the in-memory marker cache so the next editor session and next export pick up the new logo.
- Markers render as `_normalize_to_square(logo)` + colored rectangle outline drawn around the logo's alpha bbox; logo pixels are never modified, only framed.

---

## Future Considerations

### Potential Enhancements (Not Currently Planned)
- Drag-and-drop file support
- Batch folder processing
- Export to other formats (GeoJSON, GPX)
- Photo grouping/clustering for dense areas
