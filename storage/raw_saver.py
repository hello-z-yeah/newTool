"""原始串口数据实时落盘模块。

机制：串口回调 → Queue.put_nowait() → 后台写线程 → 批量写文件。
串口读取线程不会直接执行 file.write()，避免阻塞接收。
"""

import datetime
import os
import queue
import re
import threading
import time
from pathlib import Path


# Windows 非法文件名字符
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_base_name(name: str) -> str:
    """过滤 Windows 非法字符，移除末尾 .dat，空值返回 serial_data。"""
    if not name or not name.strip():
        return "serial_data"
    name = name.strip()
    # 移除末尾的 .dat（不区分大小写）
    if name.lower().endswith(".dat"):
        name = name[:-4]
    name = _ILLEGAL_CHARS.sub("_", name)
    name = name.strip(". ")
    return name if name else "serial_data"


def _format_timestamp(ts: float) -> str:
    """格式化时间戳为 yyyy-MM-dd HH:mm:ss.fff。"""
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"


def _format_data_line(data: bytes, direction: str, ts: float, display_mode: str) -> str:
    """格式化一条记录。"""
    timestamp = _format_timestamp(ts)
    tag = "RX" if direction == "rx" else "TX"

    if display_mode == "hex":
        content = data.hex(" ").upper()
    else:
        content = data.decode("utf-8", errors="replace")

    return f"{timestamp} [{tag}] {content}\n"


class RawDataSaver:
    """原始数据保存器：后台线程写文件，队列满时不阻塞串口线程。"""

    def __init__(
        self,
        queue_size: int = 5000,
        default_split_mb: int = 50,
        error_callback=None,
    ):
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._default_split_mb = default_split_mb
        self._error_callback = error_callback

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._directory: str = ""
        self._base_name: str = "serial_data"
        self._display_mode: str = "hex"
        self._split_bytes: int = default_split_mb * 1024 * 1024

        self._file = None
        self._current_path: Path | None = None
        self._current_size: int = 0
        self._segment_index: int = 0
        self._start_timestamp: str = ""

        self._dropped_records: int = 0
        self._lock = threading.Lock()

    # ---------- 公共属性 ----------

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_file(self) -> str:
        if self._current_path is not None:
            return str(self._current_path)
        return ""

    @property
    def dropped_records(self) -> int:
        return self._dropped_records

    # ---------- 启动 / 停止 ----------

    def start(
        self,
        directory: str,
        base_name: str,
        display_mode: str = "hex",
        split_mb: int | None = None,
    ):
        """启动后台写线程。"""
        if self.active:
            raise RuntimeError("存储已在运行中")

        directory = directory.strip()
        if not directory:
            raise ValueError("保存路径不能为空")

        directory_path = Path(directory)
        directory_path.mkdir(parents=True, exist_ok=True)

        # 测试目录是否可写
        test_file = directory_path / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
        except Exception as error:
            raise ValueError(f"路径不可写：{directory}（{error}）")

        self._directory = str(directory_path)
        self._base_name = _sanitize_base_name(base_name)
        self._display_mode = display_mode if display_mode in ("hex", "ascii") else "hex"

        if split_mb is not None and split_mb > 0:
            self._split_bytes = split_mb * 1024 * 1024
        else:
            self._split_bytes = self._default_split_mb * 1024 * 1024

        self._start_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._segment_index = 0
        self._current_size = 0
        self._dropped_records = 0

        # 清空队列
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        self._stop_event.clear()
        self._open_new_file()

        self._thread = threading.Thread(target=self._write_loop, daemon=True)
        self._thread.start()

    def stop(self, flush: bool = True):
        """停止写线程。flush=True 时排空队列再关闭文件。"""
        if not self.active:
            return

        self._stop_event.set()

        if flush:
            # 通知写线程排空队列后退出
            self._queue.put(None)  # sentinel

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                    self._file.close()
                except Exception:
                    pass
                self._file = None

    # ---------- 入队 ----------

    def enqueue_rx(self, data: bytes, timestamp: float):
        """入队一条 RX 记录。不阻塞串口线程。"""
        if not self.active:
            return
        try:
            self._queue.put_nowait(("rx", data, timestamp))
        except queue.Full:
            self._dropped_records += 1
            self._notify_error(f"存储队列已满，已丢弃 {self._dropped_records} 条记录")

    def enqueue_tx(self, data: bytes, timestamp: float):
        """入队一条 TX 记录。不阻塞串口线程。"""
        if not self.active:
            return
        try:
            self._queue.put_nowait(("tx", data, timestamp))
        except queue.Full:
            self._dropped_records += 1
            self._notify_error(f"存储队列已满，已丢弃 {self._dropped_records} 条记录")

    # ---------- 内部方法 ----------

    def _open_new_file(self):
        """打开新的存储文件。"""
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass

        if self._segment_index == 0:
            filename = f"{self._base_name}_{self._start_timestamp}.dat"
        else:
            filename = f"{self._base_name}_{self._start_timestamp}_{self._segment_index:03d}.dat"

        self._current_path = Path(self._directory) / filename
        self._current_size = 0
        self._segment_index += 1

        # 以二进制追加模式打开，便于准确计算文件大小
        self._file = open(self._current_path, "ab")

    def _write_loop(self):
        """后台写线程主循环。"""
        while True:
            try:
                record = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue

            if record is None:
                # sentinel：排空剩余记录后退出
                break

            direction, data, timestamp = record
            line = _format_data_line(data, direction, timestamp, self._display_mode)
            line_bytes = line.encode("utf-8")

            with self._lock:
                if self._file is None:
                    continue

                try:
                    self._file.write(line_bytes)
                    self._current_size += len(line_bytes)

                    # 检查是否需要分割
                    if self._current_size >= self._split_bytes:
                        self._file.flush()
                        self._file.close()
                        self._open_new_file()
                except Exception as error:
                    self._notify_error(f"写入文件失败：{error}")

        # 排空队列中剩余记录
        while True:
            try:
                record = self._queue.get_nowait()
            except queue.Empty:
                break
            if record is None:
                continue
            direction, data, timestamp = record
            line = _format_data_line(data, direction, timestamp, self._display_mode)
            line_bytes = line.encode("utf-8")
            with self._lock:
                if self._file is not None:
                    try:
                        self._file.write(line_bytes)
                        self._current_size += len(line_bytes)
                    except Exception:
                        pass

        # 最终关闭文件
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                    self._file.close()
                except Exception:
                    pass
                self._file = None

    def _notify_error(self, message: str):
        """通过回调通知 UI 错误（不直接弹 MessageBox）。"""
        if self._error_callback is not None:
            try:
                self._error_callback(message)
            except Exception:
                pass
