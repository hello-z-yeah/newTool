from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import ComboBox, SwitchButton

class SerialPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Port selection
        port_layout = QHBoxLayout()
        port_label = QLabel("Port:")
        self.port_combo = ComboBox()
        self.port_combo.addItems(["COM1", "COM2", "COM3"])
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_combo)

        # Baud rate selection
        baud_layout = QHBoxLayout()
        baud_label = QLabel("Baud:")
        self.baud_combo = ComboBox()
        self.baud_combo.addItems(["9600", "115200", "256000"])
        baud_layout.addWidget(baud_label)
        baud_layout.addWidget(self.baud_combo)

        # Start/Stop switch
        self.switch = SwitchButton("Start", "Stop")
        self.switch.setChecked(False)

        layout.addLayout(port_layout)
        layout.addLayout(baud_layout)
        layout.addWidget(self.switch)
        layout.addStretch()
