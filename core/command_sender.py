"""Command building and serial sending without any UI dependencies."""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from protocol_parser.parser import calc_checksum, parse_hex_input


_CHECKSUM_ALIASES = {
    "ADD8": "add8",
    "SUM": "add8",
    "XOR": "xor",
    "XOR8": "xor",
    "CRC16": "crc16_modbus",
    "CRC16_MODBUS": "crc16_modbus",
    "MODBUS": "crc16_modbus",
    "CRC8": "crc8",
    "CRC16_CCITT": "crc16_ccitt",
    "CRC32": "crc32",
}


def parse_fields_json(text: str) -> dict[str, Any] | list[Any] | None:
    content = str(text or "").strip()
    if not content:
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"字段 JSON 格式错误：{exc.msg}（第 {exc.lineno} 行）") from exc
    if not isinstance(value, (dict, list)):
        raise ValueError("字段 JSON 必须是对象或数组")
    return value


def normalize_direction(value: str) -> str:
    text = str(value or "").strip().lower()
    response_markers = ("response", "响应", "主机发送", "mcu发送", "mcu 发送")
    return "response" if any(marker in text for marker in response_markers) else "request"


def extract_command_code(value: str | int) -> int:
    if isinstance(value, int):
        return value & 0xFF
    text = str(value or "").strip()
    if not text:
        raise ValueError("请选择命令")
    token = text.split()[0]
    try:
        return int(token, 0) & 0xFF
    except ValueError:
        import re
        match = re.search(r"0x([0-9a-fA-F]+)", text)
        if not match:
            raise ValueError(f"无法从命令中解析命令字：{text}")
        return int(match.group(1), 16) & 0xFF


def build_hex_payload(
    text: str,
    *,
    append_checksum: bool = False,
    checksum_algorithm: str = "ADD8",
    append_crlf: bool = False,
) -> bytes:
    payload = parse_hex_input(text)
    if append_checksum:
        label = str(checksum_algorithm or "ADD8").strip().upper().replace("-", "_")
        algorithm = _CHECKSUM_ALIASES.get(label, checksum_algorithm)
        payload += calc_checksum(payload, algorithm)
    if append_crlf:
        payload += b"\r\n"
    return payload


def build_ascii_payload(text: str, *, append_crlf: bool = False) -> bytes:
    value = str(text if text is not None else "")
    if value == "":
        raise ValueError("请输入 ASCII 内容")
    if append_crlf and not value.endswith(("\r\n", "\n")):
        value += "\r\n"
    return value.encode("utf-8", errors="replace")


class CommandSender:
    """Send bytes through the application's already-open serial worker."""

    def __init__(
        self,
        send_bytes: Callable[[bytes], int],
        is_connected: Callable[[], bool],
        on_tx: Callable[[bytes, float], None] | None = None,
    ):
        self._send_bytes = send_bytes
        self._is_connected = is_connected
        self._on_tx = on_tx

    def send(self, payload: bytes) -> int:
        data = bytes(payload)
        if not data:
            raise ValueError("发送内容不能为空")
        if not self._is_connected():
            raise RuntimeError("请先开始监控串口后再发送")
        count = int(self._send_bytes(data) or 0)
        if count <= 0:
            raise RuntimeError("串口发送失败：未写入任何数据")
        if count != len(data):
            raise RuntimeError(f"串口仅写入 {count}/{len(data)} 字节")
        if self._on_tx is not None:
            self._on_tx(data, time.time())
        return count
