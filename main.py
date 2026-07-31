
# 兼容修改过的 customtkinter：把 apply_global_font 注入到 ctk_tk 模块命名空间
import customtkinter.windows.ctk_tk as _ctk_tk
if not hasattr(_ctk_tk, "apply_global_font"):
    def apply_global_font(widget):
        return None
    _ctk_tk.apply_global_font = apply_global_font

import argparse
from ui.app import SerialApp


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        default=None,
    )

    parser.add_argument(
        "--baud",
        default="9600",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    app = SerialApp(
        initial_port=args.port,
        initial_baud=args.baud,
    )

    app.mainloop()
