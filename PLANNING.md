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

---

## Solution: KMZ-Based Architecture

### Why KMZ?

KMZ (Keyhole Markup Zip) is Google's official format for self-contained Google Earth projects:
- It's a ZIP archive containing KML + referenced files
- Images are embedded directly in the archive
- No external hosting required
- Opens natively in Google Earth Pro
- Files can be shared via email, USB, etc.

### KMZ Structure
```
project.kmz
├── doc.kml           # Map data, placemarks, styles
└── files/
    ├── marker.png    # Custom marker icon
    ├── IMG_001.jpg   # Embedded photos
    ├── IMG_002.jpg
    └── ...
```

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Cross-platform, rich ecosystem |
| GUI | pywebview (single window) | Modern UI with embedded Google tile editor |
| Image Processing | Pillow | Industry standard, handles EXIF |
| HEIC Support | pillow-heif | Apple photo format support |
| XML Generation | ElementTree | Built into Python |
| Build | PyInstaller | Single-file executable |
| Map Editor | Google tile renderer | Tile-based map with rotation and marker edits |

### UI Notes
- pywebview hosts the single-window HTML UI and tile-based editor.
- Offline HTML export uses a stitched 2k snapshot (no API key required for deliverable).

### Why Not Web/Electron?
- Massive bundle size (100MB+ for Electron)
- Overkill for a simple utility
- Slower startup time

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    main.py (pywebview UI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ File Select  │  │   Options    │  │    Progress/Status     │ │
│  │   Dialog     │  │    Panel     │  │       Display          │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Processing Pipeline                          │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ exif_extractor  │───▶│ image_processor │───▶│kmz_generator│ │
│  │                 │    │                 │    │             │ │
│  │ - Read EXIF     │    │ - HEIC→JPG      │    │ - Build KML │ │
│  │ - Extract GPS   │    │ - Fix rotation  │    │ - Embed imgs│ │
│  │ - Get timestamp │    │ - Resize        │    │ - Create ZIP│ │
│  └─────────────────┘    │ - Compress      │    └─────────────┘ │
│                         └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   output.kmz    │
                    │  (ZIP archive)  │
                    └─────────────────┘
```

---

## Module Design

### exif_extractor.py

**Purpose**: Extract GPS and timestamp from photo EXIF data

**Key Classes**:
- `GPSCoordinates` - Dataclass with lat, lon, altitude
- `ImageMetadata` - Dataclass with GPS + timestamp

**Key Functions**:
- `get_image_metadata(path)` → `ImageMetadata`
- `is_supported_format(path)` → `bool`

**Design Notes**:
- Uses Pillow's built-in EXIF parsing
- Handles GPS stored as rationals (degrees/minutes/seconds)
- Returns `None` for missing GPS gracefully

### image_processor.py

**Purpose**: Convert and optimize images for KMZ embedding

**Key Class**: `ImageProcessor`

**Processing Steps**:
1. Open image (Pillow handles HEIC via pillow-heif plugin)
2. Apply EXIF orientation (rotate/flip to correct orientation)
3. Convert to RGB (handle RGBA, P mode transparency)
4. Resize if exceeds max dimension (maintain aspect ratio)
5. Compress as JPEG

**Design Notes**:
- EXIF orientation is applied, then stripped (prevents double-rotation)
- Uses LANCZOS resampling for high-quality resize
- Transparency converted to white background

### kmz_generator.py

**Purpose**: Generate KML/KMZ with embedded images

**Key Class**: `KMZGenerator`

**Key Function**: `create_kmz_from_files()` - High-level convenience function

**KML Structure**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Project Name</name>
    <Style id="photoStyle">
      <IconStyle>
        <Icon><href>files/marker_outlined_transparent.png</href></Icon>
      </IconStyle>
      <BalloonStyle>
        <text>$[description]</text>
      </BalloonStyle>
    </Style>
    <Folder>
      <name>Photos</name>
      <Placemark>
        <name>1</name>
        <description><![CDATA[<img src="files/photo.jpg" .../>]]></description>
        <styleUrl>#photoStyle</styleUrl>
        <Point><coordinates>lon,lat,alt</coordinates></Point>
        <TimeStamp><when>2024-01-01T12:00:00Z</when></TimeStamp>
      </Placemark>
      <!-- more placemarks... -->
    </Folder>
  </Document>
</kml>
```

**Design Notes**:
- Photos sorted chronologically before numbering
- BalloonStyle with `$[description]` removes "Directions" links
- CDATA placeholders used to avoid ElementTree escaping

---

## GUI Design

### Layout
```
┌────────────────────────────────────────────────────────────┐
│                      PicPlotter v2.0                       │
├────────────────────────────────────────────────────────────┤
│  [Select Photos]                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ✓ IMG_001.jpg                                        │  │
│  │ ✓ IMG_002.heic                                       │  │
│  │ ✗ IMG_003.jpg (No GPS)                               │  │
│  │ ✓ IMG_004.jpg                                        │  │
│  └──────────────────────────────────────────────────────┘  │
│  Selected: 4 photos (3 with GPS)                           │
├────────────────────────────────────────────────────────────┤
│  Options                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Project Name: [My Trip                            ]  │  │
│  │ Quality: [====●=====] 85%                            │  │
│  │ Output Folder: [                    ] [Browse][Reset]│  │
│  └──────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────┤
│  [====================] 100%                               │
│  Status: KMZ created successfully!                         │
│                                                            │
│                    [Create KMZ]                            │
└────────────────────────────────────────────────────────────┘
```

### User Flow
1. Click "Select Photos" → File dialog opens
2. Select JPG/HEIC files → List populates with GPS status
3. Adjust options (optional)
4. Click "Create KMZ" → Save dialog opens
5. Choose location → Progress bar animates
6. Done → Success message with file size

---

## Error Handling Strategy

| Scenario | Handling |
|----------|----------|
| No GPS data | Show ✗ in list, skip photo, report in summary |
| Unsupported format | Skip, add to error list |
| HEIC read failure | Skip, add to error list |
| All photos skipped | Show error, don't create empty KMZ |
| File locked | Exception caught, added to error list |
| Output path issue | Exception shown to user |

---

## Image Size Management

**Problem**: Raw photos can be 5-20MB each. A 50-photo KMZ would be 250MB+.

**Solution**:
- Resize to max 1920px (configurable)
- JPEG compression (25-100% quality slider)
- Result: ~100-500KB per photo
- 50 photos → ~10-25MB KMZ

**Estimate Display**: Before export, estimate is shown based on:
```
pixels × (0.3 + quality/100 × 0.7) bytes/pixel
```

---

## Build Configuration

### PyInstaller Options
```python
args = [
    "--onefile",           # Single executable
    "--windowed",          # No console window
    "--clean",             # Clean cache
    "--hidden-import=pillow_heif",
    "--hidden-import=PIL",
    "--add-data=assets/marker_outlined_transparent.png;assets",
]
```

### Why `--onefile`?
- Simpler distribution (one file to share)
- No DLL dependencies to manage
- Trade-off: Slightly slower startup (unpacks to temp)

### Asset Bundling
Assets are extracted to `sys._MEIPASS` at runtime. The `get_asset_path()` function handles path resolution for both development and frozen modes.

---

## Future Considerations

### Potential Enhancements (Not Currently Planned)
- Drag-and-drop file support
- Folder batch processing
- Preview map before export
- Custom placemark icons per photo
- Export to other formats (GeoJSON, GPX)
- Photo grouping/clustering for dense areas

### Known Limitations
- Windows only (could support macOS/Linux with same codebase)
- Requires Google Earth Pro for viewing (free download)
- Large photos may take time to process
