"""PySide6 launcher for the serial protocol parsing tool."""
from __future__ import annotations

import argparse
import faulthandler
import sys

# 开启崩溃栈回溯：如果拖放/重建cellWidget期间仍有C++崩溃，
# 命令行会输出更明确的调用栈；稳定后也无副作用，永久保留。
faulthandler.enable()

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui.app import SerialApp
from ui.theme import UI_FONT_FAMILY, UI_FONT_POINT_SIZE, UI_FONT_WEIGHT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", default="9600")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("串口协议解析工具")
    app.setOrganizationName("SerialPortDataParsing")

    # 整个程序统一主字体；实时数据框单独使用 ZoomableDataView 管理可缩放字号
    app_font = QFont(UI_FONT_FAMILY)
    app_font.setPointSize(max(1, int(UI_FONT_POINT_SIZE)))
    try:
        app_font.setWeight(QFont.Weight(UI_FONT_WEIGHT))
    except (TypeError, ValueError):
        app_font.setWeight(QFont.Weight.DemiBold)
    app.setFont(app_font)

    window = SerialApp(initial_port=args.port, initial_baud=args.baud)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
