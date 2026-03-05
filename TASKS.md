# TASKS.md - Task Tracking and Status

**Related Docs**: [CLAUDE.md](./CLAUDE.md) | [PLANNING.md](./PLANNING.md)

---

## Project Status: Feature Complete

All planned features have been implemented. The application is ready for Windows build and distribution.

**Current Notes**
- Single-window pywebview app with embedded tile-based editor view
- Offline HTML export uses a stitched 2k snapshot (no API key required)
- Tile-based preview matches the export snapshot
- Manual placement for non-GPS photos and per-photo group labels in the editor

---

## Completed Tasks

### Phase 1: Project Setup
- [x] Create project structure
- [x] Set up requirements.txt
- [x] Create `__init__.py` for package

### Phase 2: EXIF/GPS Extraction
- [x] Implement `exif_extractor.py`
- [x] Extract GPS coordinates from EXIF
- [x] Handle JPG and HEIC formats
- [x] Convert GPS rationals to decimal degrees
- [x] Extract timestamp for chronological sorting

### Phase 3: Image Processing
- [x] Implement `image_processor.py`
- [x] HEIC to JPG conversion
- [x] Image resizing (max 1920px)
- [x] JPEG compression (configurable quality)
- [x] EXIF orientation handling (all 8 values)

### Phase 4: KMZ Generation
- [x] Implement `kmz_generator.py`
- [x] Generate KML XML with placemarks
- [x] Create KMZ (ZIP) archive
- [x] Embed images in `files/` directory
- [x] Add custom marker icon support
- [x] Sort photos chronologically
- [x] Fix CDATA escaping issue (placeholder approach)

### Phase 5: GUI Implementation
- [x] Implement `main.py` with Tkinter
- [x] File selection dialog (multi-select)
- [x] Photo list with GPS status (✓/✗)
- [x] Options panel (project name, quality, output folder)
- [x] Progress bar
- [x] Status messages
- [x] Output folder selection with Browse/Reset

### Phase 6: Build System
- [x] Create `build/build.py` PyInstaller script
- [x] Create `build_windows.bat` convenience script
- [x] Create `run.bat` for development
- [x] Bundle custom marker asset

### UI/UX Refinements
- [x] Remove text under thumbnail (filename, date, location, altitude)
- [x] Increase thumbnail size to 800px max-width
- [x] Quality slider range: 25-100% (was 60-100%)
- [x] Default export quality set to 30% with updated UI label
- [x] Remove "Directions: To here - From here" from balloon (BalloonStyle)
- [x] Fix thumbnail not displaying (CDATA escaping fix)
- [x] Switch from numbered balloon icons to regular markers
- [x] Use custom transparent marker (`marker_outlined_transparent.png`)
- [x] Add photo thumbnails with hover preview in the photo list
- [x] Move group color dot to the right side of photo rows and enlarge

### HTML Map Enhancements
- [x] Add marker size slider (48-192px range) with live preview
- [x] Display actual marker PNG in calibration preview (replaces colored dots)
- [x] Proportional font sizing for marker numbers
- [x] Visual distinction between calibration and preview markers (75% size, 70% opacity)
- [x] Add client info block to export header and reorder proposal link
- [x] Update "How to Use" panel with icons and clearer instruction copy
- [x] Replace legend checkboxes with color-matched eye toggles

### Phase 7: CustomTkinter UI Modernization
- [x] Migrate from Tkinter/TTK to CustomTkinter framework
- [x] Implement dark theme with consistent color palette
- [x] Custom `FileListItem` and `FileListWidget` classes for main app
- [x] Custom `CalibrationPhotoItem` and `CalibrationPhotoList` classes for calibration dialog
- [x] Modern rounded buttons, sliders, progress bars, and radio buttons
- [x] Update PyInstaller spec for CustomTkinter asset bundling (onedir mode)
- [x] Update requirements.txt with customtkinter and darkdetect dependencies

### Phase 8: Single-Window Architecture
- [x] Convert CalibrationDialog to CalibrationView (CTkFrame instead of CTkToplevel)
- [x] Implement view switching in main.py (PicPlotter view ↔ Calibration view)
- [x] Add window resizing when switching views (780x680 ↔ 1050x750)
- [x] Add prepare() and reset() methods for view state management

### Phase 9: Groups + Manual Plotting
- [x] Enable manual placement for non-GPS photos in the editor
- [x] Allow re-plotting any photo via marker drag
- [x] Persist group labels and placements in overrides
- [x] Include manual placements in KMZ/HTML exports
- [x] Update main view counts to include manual placements

### Phase 10: Performance & Code Cleanup (Jan 2026)
- [x] Fix triple image open in `exif_extractor.py` (~3x faster metadata extraction)
- [x] Vectorize marker colorization with NumPy (10-50x faster)
- [x] Centralize constants in `config.py` (TILE_SIZE, EXPORT_MAX_DIM, etc.)
- [x] Consolidate `get_asset_path()` into `config.py` (was duplicated in 3 files)
- [x] Remove `format_file_size()` duplication from `image_processor.py`
- [x] Delete unused legacy files (~3,000 lines removed):
  - `map_editor_app.py` (511 lines)
  - `auto_map_view.py` (1,158 lines)
  - `google_maps.py` (187 lines)
  - `calibration_dialog.py` (1,210 lines)
- [x] Clean up `coordinate_transform.py` (removed unused calibration functions)
- [x] Parallelize image processing with ThreadPoolExecutor (2-4x faster exports)

---

## Pending: Build on Windows

The code is complete. The final step is to build the Windows executable:

```cmd
cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_auto_gpt
pip install -r requirements.txt
pyinstaller PicPlotter.spec --clean
```

**Important**: This must be run on Windows Command Prompt. Windows accesses WSL files directly via `\\wsl$\`.

**Note**: The app uses pywebview and is built in `onedir` mode. Output is in `dist/PicPlotterAuto/` folder.
**Note**: `pythonnet` is required for pywebview when running from source on Windows.

---

## Testing Checklist

Before distribution, verify:

- [ ] App launches without errors
- [ ] File selection dialog works
- [ ] JPG photos with GPS are detected correctly
- [ ] HEIC photos with GPS are detected correctly
- [ ] Photos without GPS show --- until manually placed
- [ ] Quality slider affects output file size
- [ ] Output folder selection works
- [ ] Map editor opens when clicking "Open Map Editor"
- [ ] Marker drag updates positions
- [ ] Manual placement works for photos without GPS
- [ ] Group labels persist across editor sessions
- [ ] Rotation preview matches export output
- [ ] Offline HTML export opens without internet
- [ ] KMZ is created successfully
- [ ] KMZ opens in Google Earth Pro
- [ ] Placemarks appear at correct locations
- [ ] Clicking placemark shows photo thumbnail
- [ ] No "Directions" text in balloon
- [ ] Custom marker icon displays correctly
- [ ] Photos are numbered chronologically

---

## Known Issues

None currently identified.

---

## Version History

### v2.5.0 (Current)
- Performance optimizations: 3x faster metadata extraction, parallel image processing
- Code cleanup: removed ~3,000 lines of dead code
- Centralized constants and utilities in config.py
- NumPy-vectorized marker colorization (10-50x faster)

### v2.4.0
- Manual placement for any photo (including non-GPS)
- Group labels in the map editor

### v2.2.0
- Single-window architecture with view switching
- Calibration view embedded in main window (no longer a separate dialog)
- Dynamic window resizing when switching between views

### v2.1.0
- Modern dark-themed UI with CustomTkinter
- Rounded widgets, buttons, and sliders
- Custom styled file list and photo selection components
- Improved visual consistency across all dialogs

### v2.0.0
- Complete rebuild from v1.0
- KMZ-based architecture (no cloud dependencies)
- Single executable distribution
- HEIC support
- EXIF orientation handling
- Custom marker icons
- Chronological photo ordering

### v1.0.0 (Legacy)
- Google Cloud OAuth + Drive integration
- Required complex setup process
- Two separate executables
- Internet-dependent

---

## File Locations

| Description | WSL Path | Windows Path |
|-------------|----------|--------------|
| Source code | `/home/rkinder9168/projects/PicPlotter_v2/src/` | `\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_v2\src\` |
| Assets | `/home/rkinder9168/projects/PicPlotter_v2/assets/` | `\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_v2\assets\` |
| PyInstaller spec | `/home/rkinder9168/projects/PicPlotter_v2/PicPlotter.spec` | `\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_v2\PicPlotter.spec` |
| Build output | `/home/rkinder9168/projects/PicPlotter_v2/dist/PicPlotter/` | `\\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_v2\dist\PicPlotter\` |

WSL is the single source of truth. Windows accesses files directly via `\\wsl$\Ubuntu\...`.

---

## Quick Commands

### Run from source (Windows)
```cmd
cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_v2
python src/main.py
```

### Build executable (Windows)
```cmd
cd \\wsl$\Ubuntu\home\rkinder9168\projects\PicPlotter_v2
pyinstaller PicPlotter.spec --clean
```

### Verify syntax (WSL)
```bash
python3 -m py_compile /home/rkinder9168/projects/PicPlotter_v2/src/*.py
```

---

## Future Enhancement Ideas

These are not planned but could be considered:

1. **Drag-and-drop** - Allow dropping files onto the window
2. **Folder processing** - Process entire folders recursively
3. **Preview map** - Show map preview before export
4. **Photo info tooltips** - Hover to see GPS, date, etc.
5. **Batch presets** - Save/load quality/size settings
6. **Multi-language** - Localization support
7. **macOS build** - Test and package for macOS
8. **Photo clustering** - Group nearby photos for dense areas
9. **Custom balloon templates** - User-defined HTML templates
10. **Export formats** - GeoJSON, GPX, HTML map
