"""
Serial control panel using PySide6 + qfluentwidgets.
Provides:
- ComboBox for serial port list (list_serial_ports)
- ComboBox for baud rates (common rates)
- SwitchButton to start/stop
- PlainTextEdit to show live RX data (log)
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPlainTextEdit
from qfluentwidgets import SwitchButton

from protocol_parser.serial_collector import SerialCollector, list_serial_ports

class SerialPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.collector: SerialCollector | None = None

        # UI layout
        layout = QVBoxLayout(self)

        # Port / baud selection
        select_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.addItems(list_serial_ports())
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        select_layout.addWidget(QLabel("Port:"), 0)
        select_layout.addWidget(self.port_combo, 1)
        select_layout.addWidget(QLabel("Baud:"), 0)
        select_layout.addWidget(self.baud_combo, 1)

        # Start / Stop switch
        self.toggle = SwitchButton(self)
        self.toggle.setChecked(False)
        self.toggle.toggled.connect(self._on_toggle)

        # Live RX log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        layout.addLayout(select_layout)
        layout.addWidget(QLabel("Live RX:"), 0)
        layout.addWidget(self.log_view, 1)
        layout.addWidget(self.toggle, 0, alignment=Qt.AlignRight)

    def _on_toggle(self, checked: bool):
        if checked:
            port = self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            self.collector = SerialCollector(port, baud)
            self.collector.on_frame = self._on_frame
            self.collector.start()
            self.log_view.appendPlainText(f"[Started] {port} @ {baud}")
        else:
            if self.collector:
                self.collector.stop()
                self.log_view.appendPlainText("[Stopped]")
                self.collector = None

    def _on_frame(self, raw: bytes, parsed):
        # Show raw hex string; parsed dict is optional
        hex_str = " ".join(f"{b:02X}" for b in raw)
        self.log_view.appendPlainText(hex_str)
        # Auto‑scroll to bottom
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def get_collector(self) -> SerialCollector | None:
        return self.collector
