
import threading
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial=None

class SerialWorker:
    def __init__(self, callback=None):
        self.callback=callback
        self.ser=None
        self.running=False

    def scan_ports(self):
        """扫描全部串口，返回包含完整信息的列表。

        返回结构示例::

            [
                {
                    "device": "COM14",
                    "display_name": "COM14 - USB-Enhanced-SERIAL-D",
                    "description": "USB-Enhanced-SERIAL-D",
                    "manufacturer": "WCH",
                    "hwid": "USB VID:PID=1A86:55D4"
                }
            ]

        ``device`` 永远是真实端口号，``display_name`` 仅用于界面显示，
        实际打开串口时必须只传入 ``device``。
        """
        ports = []

        if not serial:
            return ports

        for port in serial.tools.list_ports.comports():
            device = port.device
            description = port.description or ""
            manufacturer = port.manufacturer or ""

            # 清理无效描述
            if description.lower() in ("n/a", "unknown", "none"):
                description = ""

            parts = [device]

            if description and device.lower() not in description.lower():
                parts.append(description)

            if (
                manufacturer
                and manufacturer.lower() not in description.lower()
            ):
                parts.append(manufacturer)

            display_name = " - ".join(parts)

            ports.append({
                "device": device,
                "display_name": display_name,
                "description": description,
                "manufacturer": manufacturer,
                "hwid": port.hwid or "",
            })

        return ports

    def connect(self, port, baud=9600):
        if not serial:
            raise RuntimeError("请安装 pyserial")
        self.ser=serial.Serial(port, baud, timeout=0.1)
        self.running=True
        threading.Thread(target=self.receive_loop,daemon=True).start()

    def receive_loop(self):
        while self.running:
            if self.ser and self.ser.in_waiting:
                data=self.ser.read(self.ser.in_waiting)
                if self.callback:
                    self.callback(data)

    def send(self,data):
        if self.ser:
            self.ser.write(data)

    def close(self):
        self.running=False
        if self.ser:
            self.ser.close()
