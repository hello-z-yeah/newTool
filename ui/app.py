"""
PySide6 + qFluentWidgets front‑end for the Serial‑Port‑Data‑Parsing tool.

The UI provides:
* A toolbar with port / baud selection (placeholder for future serial support).
* A hex‑input field with 300 ms debounce.
* “Parse” button – runs protocol_parser.parse_frame on the entered hex.
* Result view – shows a nicely formatted description of the parsed frame.
* Command library panel – loads the built‑in commands from the JSON protocol file.
* Theme toggle (light / dark) using qfluentwidgets.

All heavy lifting (checksum, frame split, attribute handling) stays in
`protocol_parser`.  The UI only formats and displays the data.
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentWindow, Theme, setTheme, isDarkTheme

# Import the core parser package (already present in the repo)
from protocol_parser import (
    load_protocol,
    get_builtin_v3,
    merge_protocol,
    parse_hex_input,
    split_frame,
    classify_protocol_error,
    _log_error_to_disk,
)

# UI components
from ui.main_window import MainWindow


def load_protocol_cfg() -> dict:
    """Load the user‑provided protocol JSON (if any) and merge it with the built‑in V3.0."""
    builtin = get_builtin_v3()
    custom_path = Path(__file__).resolve().parent.parent / "product" / "v3_serial.json"
    if custom_path.exists():
        try:
            custom = load_protocol(custom_path)
            return merge_protocol(builtin, custom)
        except Exception as exc:  # pragma: no cover
            _log_error_to_disk(exc)
    return builtin


def main() -> int:
    """Standard Qt entry point."""
    app = QApplication(sys.argv)
    cfg = load_protocol_cfg()
    win = MainWindow(protocol_cfg=cfg)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
