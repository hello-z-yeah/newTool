from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel
from qfluentwidgets import SwitchButton
from protocol_parser.serial_collector import SerialCollector

class TxPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.collector: SerialCollector | None = None
        self.tx_counter = 0
        layout = QHBoxLayout(self)
        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText("Enter HEX to send, e.g. AA BB CC")
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._on_send)
        self.counter_label = QLabel("TX: 0")
        layout.addWidget(self.hex_input, 1)
        layout.addWidget(self.send_btn)
        layout.addWidget(self.counter_label)

    def set_collector(self, collector: SerialCollector | None):
        """Inject the SerialCollector that SerialPanel created."""
        self.collector = collector

    def _on_send(self):
        if not self.collector:
            self.hex_input.setText("[Not connected]")
            return
        text = self.hex_input.text().strip()
        if not text:
            return
        try:
            from protocol_parser import parse_hex_input
            data = parse_hex_input(text)
            self.collector.send(data)
            self.tx_counter += 1
            self.counter_label.setText(f"TX: {self.tx_counter}")
            self.hex_input.clear()
        except Exception as e:
            self.hex_input.setText(f"[Error: {e}]")
