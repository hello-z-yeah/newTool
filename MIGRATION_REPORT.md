# PySide6 migration report

## Runtime framework

- Replaced the CustomTkinter/Tkinter window, layouts and widgets with PySide6.
- `requirements.txt` no longer contains `customtkinter` or Pillow.
- The protocol parser, serial worker, raw saver and command-library storage are
  retained as framework-independent backend modules.

## UI retained

- Five independent white cards: navigation, serial configuration, live data,
  send area and status information.
- Expandable serial configuration and live serial reconfiguration.
- HEX/ASCII live display, escaped ASCII control bytes, packet display timeout,
  protocol parsing, Word protocol import and protocol inspection.
- 30 ms receive batching, 5,000-block receive cap and background raw saving.
- Editable 40-row HEX/ASCII command libraries, row send buttons, cycle sending
  and inline add/update/delete.
- Protocol/HEX/ASCII send modes, CRLF, checksum and automatic sending.
- Hover-only vertical scroll bars when the content actually overflows.
- Three-state QPushButton styling and persistent checked styling for toggle and
  mode buttons.

## Verification performed in the migration environment

- Python syntax compilation passed for the launcher, UI, backend and tests.
- All five existing backend command-library/command-sender unit tests passed.
- PySide6 is not installed in the build container, so a live Qt window could
  not be opened there. Install the included requirements on Windows and run
  `python main.py` for visual/device testing.

## 2026-08-02 control-style correction

- Added explicit SVG chevrons for every `QComboBox`, including editable baud-rate input.
- Replaced native Windows `QSpinBox`/`QDoubleSpinBox` stepper subcontrols with QSS-styled 24 px buttons.
- Added hover and pressed feedback matching the application's white/gray/blue control language.
- Arrow asset paths are resolved from `ui/theme.py`, so the application does not depend on the launch directory.
