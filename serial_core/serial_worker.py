
import re
import threading
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


INVALID_PORT_TEXT = {
    "",
    "n/a",
    "none",
    "unknown",
    "standard",
}


def _clean_port_text(value, device=""):
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    # 删除描述中重复出现的端口号，例如：
    # USB-SERIAL CH340 (COM14) -> USB-SERIAL CH340
    text = re.sub(
        rf"\s*\({re.escape(device)}\)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    # 删除开头重复出现的 COM 号
    text = re.sub(
        rf"^{re.escape(device)}\s*[-:]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    if text.lower() in INVALID_PORT_TEXT:
        return ""

    return text


def _build_port_display_name(port):
    device = str(port.device).strip()

    product = _clean_port_text(
        getattr(port, "product", ""),
        device,
    )

    description = _clean_port_text(
        getattr(port, "description", ""),
        device,
    )

    interface = _clean_port_text(
        getattr(port, "interface", ""),
        device,
    )

    manufacturer = _clean_port_text(
        getattr(port, "manufacturer", ""),
        device,
    )

    # 优先使用真正的设备名称
    friendly_name = (
        product
        or description
        or interface
    )

    # 厂商只作为最后回退
    if not friendly_name:
        friendly_name = manufacturer

    # 全部为空时，最后显示 VID/PID
    if not friendly_name:
        vid = getattr(port, "vid", None)
        pid = getattr(port, "pid", None)

        if vid is not None and pid is not None:
            friendly_name = (
                f"USB VID:PID={vid:04X}:{pid:04X}"
            )

    if friendly_name:
        return f"{device} - {friendly_name}"

    return device


class SerialWorker:
    def __init__(self, callback=None, error_callback=None):
        self.callback = callback
        self.error_callback = error_callback

        self._serial = None
        self._read_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._operation_lock = threading.RLock()

    @property
    def is_connected(self):
        return (
            self._serial is not None
            and self._serial.is_open
            and not self._stop_event.is_set()
        )

    def scan_ports(self):
        """扫描全部串口，返回包含完整信息的列表。

        返回结构示例::

            [
                {
                    "device": "COM14",
                    "display_name": "COM14 - USB-SERIAL CH340",
                    "description": "USB-SERIAL CH340",
                    "product": "USB-SERIAL CH340",
                    "manufacturer": "wch.cn",
                    "interface": "",
                    "hwid": "USB VID:PID=1A86:7523"
                }
            ]

        ``device`` 永远是真实端口号，``display_name`` 仅用于界面显示，
        实际打开串口时必须只传入 ``device``。
        """
        results = []

        if not serial:
            return results

        ports = list(serial.tools.list_ports.comports())

        DEBUG_PORT_SCAN = False

        if DEBUG_PORT_SCAN:
            for port in ports:
                print(
                    {
                        "device": port.device,
                        "name": getattr(port, "name", None),
                        "description": getattr(port, "description", None),
                        "product": getattr(port, "product", None),
                        "manufacturer": getattr(port, "manufacturer", None),
                        "interface": getattr(port, "interface", None),
                        "hwid": getattr(port, "hwid", None),
                    }
                )

        def port_sort_key(port):
            match = re.search(
                r"COM(\d+)",
                str(port.device),
                re.IGNORECASE,
            )
            if match:
                return int(match.group(1))
            return 999999

        ports.sort(key=port_sort_key)

        for port in ports:
            results.append({
                "device": str(port.device),
                "display_name": _build_port_display_name(port),
                "description": (
                    getattr(port, "description", "") or ""
                ),
                "product": (
                    getattr(port, "product", "") or ""
                ),
                "manufacturer": (
                    getattr(port, "manufacturer", "") or ""
                ),
                "interface": (
                    getattr(port, "interface", "") or ""
                ),
                "hwid": (
                    getattr(port, "hwid", "") or ""
                ),
            })

        return results

    def connect(self, port, baudrate=9600, data_bits=8, stop_bits=1):
        if not serial:
            raise RuntimeError("请安装 pyserial")

        with self._operation_lock:
            # 防止重复启动两个读取线程
            self.disconnect(wait=True, timeout=1.0)

            bytesize_map = {
                5: serial.FIVEBITS,
                6: serial.SIXBITS,
                7: serial.SEVENBITS,
                8: serial.EIGHTBITS,
            }

            stopbits_map = {
                1.0: serial.STOPBITS_ONE,
                1.5: serial.STOPBITS_ONE_POINT_FIVE,
                2.0: serial.STOPBITS_TWO,
            }

            with self._lock:
                self._stop_event.clear()

                self._serial = serial.Serial(
                    port=port,
                    baudrate=int(baudrate),
                    bytesize=bytesize_map.get(
                        int(data_bits),
                        serial.EIGHTBITS,
                    ),
                    stopbits=stopbits_map.get(
                        float(stop_bits),
                        serial.STOPBITS_ONE,
                    ),
                    timeout=0.1,
                    write_timeout=1.0,
                )

                self._read_thread = threading.Thread(
                    target=self._read_loop,
                    daemon=True,
                    name=f"serial-reader-{port}",
                )
                self._read_thread.start()

    def reconnect(self, port, baudrate=9600, data_bits=8, stop_bits=1, timeout=2.0):
        with self._operation_lock:
            self.disconnect(wait=True, timeout=timeout)
            self.connect(
                port=port,
                baudrate=baudrate,
                data_bits=data_bits,
                stop_bits=stop_bits,
            )

    def _read_loop(self):
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    ser = self._serial

                if ser is None or not ser.is_open:
                    break

                waiting = ser.in_waiting

                data = ser.read(
                    waiting if waiting > 0 else 1
                )

                if data and not self._stop_event.is_set():
                    # 短暂聚合后续字节，避免每个字节单独一行
                    time.sleep(0.002)

                    more = ser.in_waiting

                    if more > 0:
                        data += ser.read(more)

                if (
                    data
                    and not self._stop_event.is_set()
                    and self.callback is not None
                ):
                    # 数据实际到达时生成时间戳（完整帧后才取当前系统时间
                    received_at = time.time()

                    try:
                        self.callback(
                            bytes(data),
                            received_at,
                        )
                    except TypeError:
                        # 兼容仅接受 data 1 个参数的旧回调签名
                        try:
                            self.callback(bytes(data))
                        except Exception:
                            pass

            except (serial.SerialException, OSError) as error:
                # 用户主动停止时，close 导致的异常不需要报告
                if not self._stop_event.is_set():
                    if self.error_callback is not None:
                        try:
                            self.error_callback(error)
                        except Exception:
                            pass
                break

    def send(self, data):
        with self._lock:
            if self._serial is not None and self._serial.is_open:
                return self._serial.write(data)
        return 0

    def disconnect(self, wait=True, timeout=2.0):
        with self._operation_lock:
            self._stop_event.set()

            with self._lock:
                ser = self._serial
                thread = self._read_thread
                self._serial = None
                self._read_thread = None

        if ser is not None:
            try:
                if ser.is_open:
                    ser.cancel_read()
            except (AttributeError, serial.SerialException, OSError):
                pass

            try:
                if ser.is_open:
                    ser.close()
            except (serial.SerialException, OSError):
                pass

        if (
            wait
            and thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=timeout)

    # 兼容旧接口
    def close(self):
        self.disconnect(wait=True, timeout=2.0)
