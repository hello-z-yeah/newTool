import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import PlainTextEdit, InfoBar

class JsonEditor(QWidget):
    """A JSON editor with 300 ms debounce validation.
    The editor validates the JSON content after the user stops typing for 300 ms
    and shows an InfoBar with success or error information.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._validate_json)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.editor = PlainTextEdit()
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor)

    def _on_text_changed(self):
        # Restart debounce timer on each change
        self._debounce_timer.start()

    def _validate_json(self):
        text = self.editor.toPlainText()
        try:
            json.loads(text)
            InfoBar.success(
                title="Valid JSON",
                content="The JSON is syntactically correct.",
                duration=1500,
                parent=self,
            )
        except json.JSONDecodeError as exc:
            InfoBar.error(
                title="Invalid JSON",
                content=str(exc),
                duration=3000,
                parent=self,
            )
