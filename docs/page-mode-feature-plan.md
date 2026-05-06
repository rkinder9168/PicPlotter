# Page Mode Feature Plan

## Summary

- Add a `Group | Page` segmented toggle in the current Groups panel location. Only the active mode's controls, assignments, and labels are visible.
- Preserve existing Group behavior unchanged. Page mode uses page names and assignments, but all markers use the standard logo with no colored border or page-specific logo styling.
- Page mode editor adds an in-editor page selector. Each page owns its own background choice, view/rotation, and marker placements.
- Page-mode exports generate a multi-page interactive deliverable with page navigation, one background per page, and a legend that lists the active page's photo numbers/names.

## Key Changes

- Data/state:
  - Add `assignment_mode: "group" | "page"` to app state and persisted overrides.
  - Add page assignment models alongside current groups: page id, name/display name, assigned photo paths, and per-page editor state.
  - Keep inactive mode data preserved, but only the active mode affects main UI, editor, exports, and deploys.
  - Make Page 1 the locked default page; deleting another page moves its photos to Page 1.
- UI in `assets/app.html`:
  - Replace the static `Groups` heading with a `Group | Page` toggle.
  - Group mode keeps color swatches, color picker, default groups, and current marker images.
  - Page mode shows only pages, add/delete/rename/count controls, and page assignment picker; no color picker or swatches.
  - File list assignment dot becomes a neutral page/assignment icon in Page mode.
- Editor workflow:
  - In Page mode, show a page selector in the editor sidebar.
  - Switching active page swaps the editor photo list, background source, view, rotation, and placements.
  - Each page can use Auto satellite mode or Custom image mode.
  - Existing GPS, non-GPS manual placement, Custom calibration, and Custom auto-plot behavior apply per active page.
- Export/deploy:
  - Extend `src/html_map_generator.py` with a multi-page HTML generator.
  - Page-mode export payload contains an ordered `pages[]` array with page name, background image, dimensions, photos, and marker pixels.
  - Deliverable page navigation updates background, markers, lightbox scope, and legend.
  - Page-mode legend lists only the active page's photo numbers and display names.
  - Group-mode export/deploy continues using the existing single-page generator path.

## API / Types

- Add backend page APIs in `src/main.py`: `set_assignment_mode`, `get_assignment_state`, `add_page`, `delete_page`, `rename_page`, and `assign_photo_page`.
- Keep existing group APIs for compatibility, but have the frontend use neutral assignment helpers where practical.
- Add a plain marker/logo method in `src/marker_utils.py` for Page mode so no colored rectangle is drawn.
- Persist new fields in `map_overrides.json` and include them in saved project data with backward-compatible defaults for older projects.

## Test Plan

- Add focused unit tests for page assignment creation, rename/delete reassignment, sync/prune behavior, and legacy override loading.
- Add HTML generator tests for multi-page output, page navigation data, active-page legend content, and plain marker usage.
- Smoke-test manually:
  - Existing Group mode assignment, color changes, editor, export, and deploy still work.
  - Page mode with GPS photos on Auto satellite pages.
  - Page mode with non-GPS photos placed manually.
  - Page mode with Custom image pages using calibration and auto-plot.
  - Multi-page export switches pages and updates legend/lightbox correctly.

## Assumptions

- Switching modes preserves the inactive mode's data instead of deleting it.
- Page mode uses the user's configured standard logo when present, falling back to the bundled marker asset without additional page coloring.
- KMZ export remains group/placement based and does not become a multi-page deliverable unless requested separately.

## Restart Prompt

When restarting, paste:

```text
Please continue from docs/page-mode-feature-plan.md and implement the Page Mode feature in PicPlotter. Start by reading the plan and relevant group/editor/export code, then proceed with implementation and verification.
```
