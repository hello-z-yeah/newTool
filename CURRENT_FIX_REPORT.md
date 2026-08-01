# Current integrated file repair report

This repair was applied directly to the uploaded PySide6 project rather than to an older sample.

## Main changes

- Disabled the early UI geometry audit in normal runs; hidden/unlaid-out widgets no longer print false width/height warnings.
- Rewrote the optional audit so it ignores hidden/zero-size widgets and no longer treats graphics-effect paint bounds as widget geometry.
- Removed the application-wide QSS pixel font override. The application font now comes from `QApplication.setFont()` with a valid point size.
- Made `ZoomableDataView` derive from the application font and always apply a clamped positive point size, preventing `QFont::setPointSize(-1)` warnings.
- Kept Ctrl+mouse-wheel data-font zoom with a 9–22 pt limit.
- Returned layout dimensions to a compact set of shared constants and reduced excessive shadow expansion.
- Changed the send card from a too-small fixed height to content-driven sizing; ignored the large text-editor size hint so the panel stays compact without clipping its bottom row.
- Added a stable fixed table-send-button geometry and a dedicated table-button QSS variant, with the button centered vertically in every command row.
- Kept the command-library scrollbar always visible and the segmented HEX/ASCII selector intact.
- Preserved all current serial, parser, sender, storage, command-library and unified-combo features.

## Checks performed

- `python -m py_compile main.py ui/app.py ui/components.py ui/theme.py`
- `python -m unittest discover -s tests -v`
- All 5 command-library/sender tests passed.

A graphical Windows/PySide6 run is still required to verify DPI-specific appearance because PySide6 is not installed in the build container.
