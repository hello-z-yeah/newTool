"""Persistent HEX/ASCII command-library storage.

This module contains no UI code.  It is adapted from the command-library
behaviour of the legacy application and is safe to use from the current
CustomTkinter interface without rebuilding any widgets.
"""
from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


class CommandLibraryError(RuntimeError):
    """Raised when a command-library file cannot be read or written."""


class CommandLibraryStore:
    """Manage independent HEX/ASCII libraries and their cycle sequences."""

    MODES = ("hex", "ascii")
    MAX_ITEMS = 40
    FILES = {
        "hex": "hex_cmds.json",
        "ascii": "ascii_cmds.json",
        "cycle_hex": "cycle_hex.json",
        "cycle_ascii": "cycle_ascii.json",
    }

    def __init__(self, directory: str | Path, legacy_file: str | Path | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.legacy_file = Path(legacy_file) if legacy_file else None
        self._lock = threading.RLock()
        self._items: dict[str, list[dict[str, Any]]] = {"hex": [], "ascii": []}
        self._cycles: dict[str, list[dict[str, Any]]] = {"hex": [], "ascii": []}
        self.load()

    @staticmethod
    def normalize_mode(mode: str) -> str:
        value = str(mode or "").strip().lower()
        if value not in CommandLibraryStore.MODES:
            raise ValueError(f"不支持的指令库模式：{mode}")
        return value

    @staticmethod
    def _safe_delay(value: Any, default: int = 1000) -> int:
        try:
            return max(10, int(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_item(raw: Any, fallback_mode: str = "hex") -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        mode = str(raw.get("type", fallback_mode)).strip().lower()
        if mode not in CommandLibraryStore.MODES:
            mode = fallback_mode
        payload = raw.get("payload", raw.get("data", ""))
        item_id = str(raw.get("id") or uuid.uuid4().hex)
        return {
            "id": item_id,
            "name": str(raw.get("name", "")).strip(),
            "payload": str(payload if payload is not None else ""),
            "type": mode.upper(),
        }

    @staticmethod
    def _normalize_cycle_step(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            return None
        return {
            "id": item_id,
            "delay_ms": CommandLibraryStore._safe_delay(
                raw.get("delay_ms", raw.get("interval_ms", 1000))
            ),
        }

    def _path(self, key: str) -> Path:
        return self.directory / self.FILES[key]

    def _read_list(self, key: str) -> list[Any]:
        path = self._path(key)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandLibraryError(f"读取指令库失败：{path}") from exc
        if not isinstance(data, list):
            raise CommandLibraryError(f"指令库文件必须是 JSON 数组：{path}")
        return data

    @staticmethod
    def _atomic_write(path: Path, data: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise CommandLibraryError(f"保存指令库失败：{path}") from exc

    def _migrate_legacy_if_needed(self) -> None:
        if any(self._path(mode).exists() for mode in self.MODES):
            return
        if self.legacy_file is None or not self.legacy_file.exists():
            return
        try:
            raw = json.loads(self.legacy_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return
        migrated: dict[str, list[dict[str, Any]]] = {"hex": [], "ascii": []}
        for record in raw:
            inferred = str(record.get("type", "HEX")).strip().lower() if isinstance(record, dict) else "hex"
            mode = inferred if inferred in self.MODES else "hex"
            item = self._normalize_item(record, mode)
            if item is not None and len(migrated[mode]) < self.MAX_ITEMS:
                migrated[mode].append(item)
        for mode in self.MODES:
            if migrated[mode]:
                self._atomic_write(self._path(mode), migrated[mode])

    def load(self) -> None:
        with self._lock:
            self._migrate_legacy_if_needed()
            for mode in self.MODES:
                items: list[dict[str, Any]] = []
                for raw in self._read_list(mode)[: self.MAX_ITEMS]:
                    item = self._normalize_item(raw, mode)
                    if item is not None:
                        item["type"] = mode.upper()
                        items.append(item)
                self._items[mode] = items

                cycles: list[dict[str, Any]] = []
                for raw in self._read_list(f"cycle_{mode}"):
                    step = self._normalize_cycle_step(raw)
                    if step is not None:
                        cycles.append(step)
                valid_ids = {item["id"] for item in items}
                self._cycles[mode] = [step for step in cycles if step["id"] in valid_ids]

                # 把旧格式（缺少 id / 使用 data 字段）立即规范化落盘，
                # 这样生成的 id 在下次启动时保持稳定，循环配置不会失效。
                self._save_items(mode)
                self._save_cycles(mode)

    def items(self, mode: str) -> list[dict[str, Any]]:
        mode = self.normalize_mode(mode)
        with self._lock:
            return deepcopy(self._items[mode])

    def get(self, mode: str, index: int) -> dict[str, Any]:
        mode = self.normalize_mode(mode)
        with self._lock:
            return deepcopy(self._items[mode][index])

    def _save_items(self, mode: str) -> None:
        serializable = [
            {
                "id": item["id"],
                "name": item["name"],
                "payload": item["payload"],
                "type": mode.upper(),
            }
            for item in self._items[mode][: self.MAX_ITEMS]
        ]
        self._atomic_write(self._path(mode), serializable)

    def _save_cycles(self, mode: str) -> None:
        self._atomic_write(self._path(f"cycle_{mode}"), self._cycles[mode])

    def add(self, mode: str, name: str, payload: str) -> int:
        mode = self.normalize_mode(mode)
        with self._lock:
            if len(self._items[mode]) >= self.MAX_ITEMS:
                raise CommandLibraryError(f"{mode.upper()} 指令最多保存 {self.MAX_ITEMS} 条")
            item = {
                "id": uuid.uuid4().hex,
                "name": str(name or "").strip() or "未命名",
                "payload": str(payload or ""),
                "type": mode.upper(),
            }
            self._items[mode].append(item)
            self._save_items(mode)
            return len(self._items[mode]) - 1

    def update(self, mode: str, index: int, name: str, payload: str) -> None:
        mode = self.normalize_mode(mode)
        with self._lock:
            if not 0 <= index < len(self._items[mode]):
                raise IndexError("指令索引超出范围")
            self._items[mode][index]["name"] = str(name or "").strip() or "未命名"
            self._items[mode][index]["payload"] = str(payload or "")
            self._save_items(mode)

    def clear(self, mode: str, index: int) -> None:
        self.update(mode, index, "", "")

    def delete(self, mode: str, index: int) -> None:
        mode = self.normalize_mode(mode)
        with self._lock:
            if not 0 <= index < len(self._items[mode]):
                raise IndexError("指令索引超出范围")
            item_id = self._items[mode][index]["id"]
            del self._items[mode][index]
            self._cycles[mode] = [step for step in self._cycles[mode] if step["id"] != item_id]
            self._save_items(mode)
            self._save_cycles(mode)

    def cycle(self, mode: str) -> list[dict[str, Any]]:
        mode = self.normalize_mode(mode)
        with self._lock:
            return deepcopy(self._cycles[mode])

    def set_cycle(self, mode: str, steps: Iterable[dict[str, Any]]) -> None:
        mode = self.normalize_mode(mode)
        with self._lock:
            valid_ids = {item["id"] for item in self._items[mode]}
            normalized: list[dict[str, Any]] = []
            seen: set[str] = set()
            for raw in steps:
                step = self._normalize_cycle_step(raw)
                if step is None or step["id"] not in valid_ids or step["id"] in seen:
                    continue
                normalized.append(step)
                seen.add(step["id"])
            self._cycles[mode] = normalized
            self._save_cycles(mode)
