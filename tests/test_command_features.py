from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.command_library import CommandLibraryStore, CommandLibraryError
from core.command_sender import (
    CommandSender,
    build_ascii_payload,
    build_hex_payload,
    extract_command_code,
    normalize_direction,
    parse_fields_json,
)


class CommandLibraryTests(unittest.TestCase):
    def test_legacy_migration_and_cycle_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "commands.json"
            legacy.write_text(
                json.dumps(
                    [
                        {"name": "h", "type": "HEX", "data": "A5 5A"},
                        {"name": "a", "type": "ASCII", "data": "hello"},
                    ]
                ),
                encoding="utf-8",
            )
            store = CommandLibraryStore(root / "cmdlib", legacy)
            self.assertEqual(store.items("hex")[0]["payload"], "A5 5A")
            self.assertEqual(store.items("ascii")[0]["payload"], "hello")

            index = store.add("hex", "test", "01 02")
            item = store.get("hex", index)
            store.set_cycle("hex", [{"id": item["id"], "delay_ms": 1}])
            self.assertEqual(store.cycle("hex")[0]["delay_ms"], 10)
            store.delete("hex", index)
            self.assertEqual(store.cycle("hex"), [])

    def test_hex_and_ascii_each_allow_40_items(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CommandLibraryStore(
                Path(temp)
            )

            for index in range(40):
                store.add(
                    "hex",
                    f"hex-{index}",
                    "AA",
                )
                store.add(
                    "ascii",
                    f"ascii-{index}",
                    "hello",
                )

            self.assertEqual(
                len(store.items("hex")),
                40,
            )
            self.assertEqual(
                len(store.items("ascii")),
                40,
            )

            with self.assertRaises(
                CommandLibraryError
            ):
                store.add(
                    "hex",
                    "overflow",
                    "FF",
                )

            with self.assertRaises(
                CommandLibraryError
            ):
                store.add(
                    "ascii",
                    "overflow",
                    "text",
                )

    def test_empty_json_only_saves_real_items(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = CommandLibraryStore(root)
            store.add("hex", "one", "01")

            # 重新读取并检查JSON里只有1条，不是40条空字典
            reloaded = CommandLibraryStore(root)
            self.assertEqual(len(reloaded.items("hex")), 1)
            self.assertEqual(len(reloaded.items("ascii")), 0)


class CommandSenderTests(unittest.TestCase):
    def test_payload_builders(self):
        self.assertEqual(build_hex_payload("A5 5A"), b"\xA5\x5A")
        self.assertEqual(
            build_hex_payload("01 02", append_checksum=True, checksum_algorithm="ADD8"),
            b"\x01\x02\x03",
        )
        self.assertEqual(build_ascii_payload("ok", append_crlf=True), b"ok\r\n")
        self.assertEqual(extract_command_code("0x20 心跳检测"), 0x20)
        self.assertEqual(normalize_direction("主机发送"), "response")
        self.assertEqual(parse_fields_json('{"value": 1}'), {"value": 1})

    def test_sender_uses_existing_transport(self):
        sent = []
        tx = []
        sender = CommandSender(
            send_bytes=lambda data: sent.append(data) or len(data),
            is_connected=lambda: True,
            on_tx=lambda data, ts: tx.append(data),
        )
        sender.send(b"\x01\x02")
        self.assertEqual(sent, [b"\x01\x02"])
        self.assertEqual(tx, [b"\x01\x02"])


if __name__ == "__main__":
    unittest.main()
