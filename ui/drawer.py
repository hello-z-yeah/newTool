from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from qfluentwidgets import Drawer, SwitchButton, ComboBox

class SettingsDrawer(Drawer):
    """A simple settings drawer using qfluentwidgets Drawer.
    Contains a theme switch and a language selector as examples.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        # Theme switch
        theme_label = QLabel("Theme")
        theme_switch = SwitchButton("Light", "Dark")
        layout.addWidget(theme_label)
        layout.addWidget(theme_switch)

        # Language selector
        lang_label = QLabel("Language")
        lang_combo = ComboBox()
        lang_combo.addItems(["English", "中文", "Español"])
        layout.addWidget(lang_label)
        layout.addWidget(lang_combo)

        container.setLayout(layout)
        self.setWidget(container)
