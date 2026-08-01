"""协议管理器：统一管理协议加载、切换、解析和组包。

内部分别调用旧项目的 load_protocol / merge_protocol / parse_frame / encode_frame。
内置映射至少包含 "串口3.0协议" → product/v3_serial.json。
"""

import copy
import json
import os
from pathlib import Path

from .parser import (
    EncodeFrameError,
    ParseResult,
    ProtocolError,
    encode_frame,
    get_builtin_v3,
    load_protocol,
    merge_protocol,
    parse_frame,
)
from .cli import find_protocol_file
from .serial_collector import FrameSynchronizer


# 内置协议映射：显示名 → JSON 文件名（相对于 builtin_dir）
_BUILTIN_PROTOCOL_MAP = {
    "串口3.0协议": "v3_serial.json",
}


class ProtocolManager:
    """协议管理器。"""

    def __init__(self, builtin_dir: str | Path, user_dir: str | Path | None = None):
        self._builtin_dir = Path(builtin_dir).resolve()
        self._user_dir = Path(user_dir).resolve() if user_dir else None

        if self._user_dir:
            self._user_dir.mkdir(parents=True, exist_ok=True)

        # 当前协议配置
        self._current_cfg: dict | None = None
        self._current_name: str = ""

        # 已加载的协议缓存：显示名 → cfg
        self._loaded: dict[str, dict] = {}

    # ---------- 协议加载 ----------

    def load_builtin_protocols(self) -> list[str]:
        """加载所有内置协议，返回可用协议显示名列表。"""
        names = []

        for display_name, rel_path in _BUILTIN_PROTOCOL_MAP.items():
            full_path = self._builtin_dir / rel_path
            if full_path.exists():
                try:
                    cfg = self._load_and_merge(full_path)
                    self._loaded[display_name] = cfg
                    names.append(display_name)
                except Exception:
                    pass

        # 加载用户协议目录中的 JSON
        if self._user_dir:
            for json_file in sorted(self._user_dir.glob("*.json")):
                try:
                    cfg = self._load_and_merge(json_file)
                    display_name = cfg.get("product", json_file.stem)
                    self._loaded[display_name] = cfg
                    if display_name not in names:
                        names.append(display_name)
                except Exception:
                    pass

        return names

    def load_protocol_file(self, path: str | Path) -> dict:
        """加载指定路径的协议 JSON 文件。"""
        return self._load_and_merge(Path(path))

    def _load_and_merge(self, product_path: Path) -> dict:
        """加载产品协议并与内置 v3 基础协议合并。"""
        product_cfg = load_protocol(product_path)
        base_cfg = get_builtin_v3()
        merged = merge_protocol(base_cfg, product_cfg)
        return merged

    # ---------- 协议选择 ----------

    def select(self, display_name: str) -> dict:
        """选择当前协议，返回配置 dict。"""
        if display_name not in self._loaded:
            # 尝试从内置映射加载
            rel_path = _BUILTIN_PROTOCOL_MAP.get(display_name)
            if rel_path:
                full_path = self._builtin_dir / rel_path
                if full_path.exists():
                    cfg = self._load_and_merge(full_path)
                    self._loaded[display_name] = cfg

        if display_name not in self._loaded:
            raise ProtocolError(
                f"协议 '{display_name}' 未配置",
                friendly_msg=f"协议文件未配置：{display_name}",
            )

        self._current_cfg = self._loaded[display_name]
        self._current_name = display_name
        return copy.deepcopy(self._current_cfg)

    def current_config(self) -> dict | None:
        """返回当前协议配置的深拷贝。"""
        if self._current_cfg is None:
            return None
        return copy.deepcopy(self._current_cfg)

    def current_name(self) -> str:
        return self._current_name

    def available_protocols(self) -> list[str]:
        """返回可用协议显示名列表。"""
        return list(self._loaded.keys())

    # ---------- 解析和组包 ----------

    def parse_frame(self, frame: bytes, direction: str | None = None) -> ParseResult:
        """解析一个完整帧。"""
        if self._current_cfg is None:
            raise ProtocolError("未选择协议", friendly_msg="请先选择产品协议")

        return parse_frame(frame, self._current_cfg, direction=direction)

    def encode_frame(
        self,
        cmd_code,
        direction: str = "request",
        fields=None,
        data=None,
    ) -> bytes:
        """组包一个完整帧。"""
        if self._current_cfg is None:
            raise ProtocolError("未选择协议", friendly_msg="请先选择产品协议")

        return encode_frame(
            cmd_code,
            self._current_cfg,
            direction=direction,
            fields=fields,
            data=data,
        )

    # ---------- 帧同步器 ----------

    def create_synchronizer(self) -> FrameSynchronizer:
        """创建当前协议的帧同步器。"""
        if self._current_cfg is None:
            raise ProtocolError("未选择协议", friendly_msg="请先选择产品协议")
        return FrameSynchronizer(cfg=self._current_cfg)

    # ---------- 用户协议管理 ----------

    def save_user_protocol(self, cfg: dict, filename: str) -> Path:
        """保存用户协议 JSON 到用户协议目录。"""
        if self._user_dir is None:
            raise RuntimeError("未配置用户协议目录")

        safe_name = filename
        for ch in '<>:"/\\|?*':
            safe_name = safe_name.replace(ch, "_")
        if not safe_name.endswith(".json"):
            safe_name += ".json"

        path = self._user_dir / safe_name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        return path

    def add_user_protocol(self, display_name: str, cfg: dict):
        """将用户协议加入已加载列表。"""
        self._loaded[display_name] = cfg
