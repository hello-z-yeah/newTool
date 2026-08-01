"""
JSON editor widget for editing a command payload.
Features:
* QPlainTextEdit with a 300 ms debounce timer.
* Validates JSON on each debounce; if invalid, displays error in a status label.
* Exposes `get_payload()` returning a dict or None.
"""

import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel

class JsonEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._payload: dict | None = None
        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Edit JSON payload here…")
        self.status = QLabel()
        self.status.setStyleSheet("color: red")
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.status)
        # Debounce timer – 300 ms after user stops typing
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.setSingleShot(True)
        self.editor.textChanged.connect(self._timer.start)
        self._timer.timeout.connect(self._validate)

    def _validate(self):
        text = self.editor.toPlainText().strip()
        if not text:
            self._payload = None
            self.status.setText("")
            return
        try:
            self._payload = json.loads(text)
            self.status.setText("Valid JSON")
            self.status.setStyleSheet("color: green")
        except Exception as e:
            self._payload = None
            self.status.setText(f"Invalid JSON: {e}")
            self.status.setStyleSheet("color: red")

    def set_payload(self, payload: dict | None):
        """Load a dict into the editor (pretty‑printed)."""
        if payload is None:
            self.editor.clear()
            self._payload = None
            self.status.setText("")
        else:
            txt = json.dumps(payload, ensure_ascii=False, indent=2)
            self.editor.setPlainText(txt)
            self._payload = payload
            self.status.setText("Valid JSON")
            self.status.setStyleSheet("color: green")

    def get_payload(self) -> dict | None:
        return self._payload
