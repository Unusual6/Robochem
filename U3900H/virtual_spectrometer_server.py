#!/usr/bin/env python3
"""
虚拟光谱仪服务端 (U3900H Virtual Spectrometer Server)
- Flask HTTP (端口 5000): 服务端前端管理页面
- TCP Socket Server (端口 9000): 使用 U3900H 协议帧与客户端通信
  仅打印协议帧交互，不打印 HTTP 请求
"""

import json
import os
import struct
import time
import math
import random
import threading
import logging
import socket
import select
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# ==================== 抑制 Flask HTTP 请求日志 ====================
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('flask.app').setLevel(logging.ERROR)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config["SECRET_KEY"] = "u3900h_virtual_secret"
CORS(app)

# ==================== U3900H 协议编解码 ====================

STX, ETX = 0x02, 0x03


def calc_bcc(length4: bytes, payload: bytes) -> int:
    x = 0
    for v in length4 + payload + bytes([ETX]):
        x ^= v
    return x ^ STX


def encode_frame(payload_ascii: str) -> bytes:
    """将 ASCII 载荷编码为完整协议帧"""
    payload = payload_ascii.encode("ascii")
    length4 = len(payload).to_bytes(4, "big")
    bcc = calc_bcc(length4, payload)
    return bytes([STX]) + length4 + payload + bytes([ETX, bcc])


def decode_frame(data: bytes):
    """
    从字节流中解码一帧。
    返回 (payload_str, consumed_bytes)
    - 成功: (payload_ascii_str, 帧总字节数)
    - 需要更多数据: (None, 0)
    - 需要跳过无效字节: (None, skip_count)
    """
    if len(data) < 7:
        return None, 0
    if data[0] != STX:
        for i in range(1, len(data)):
            if data[i] == STX:
                return None, i
        return None, len(data)
    length = struct.unpack(">I", data[1:5])[0]
    frame_len = 7 + length  # STX(1) + Len(4) + Payload(N) + ETX(1) + BCC(1)
    if len(data) < frame_len:
        return None, 0
    if data[5 + length] != ETX:
        return None, 1  # ETX 位置不对，跳过这个 STX
    payload_bytes = data[5:5 + length]
    payload_str = payload_bytes.decode("ascii", errors="replace")
    return payload_str, frame_len


# ==================== 虚拟光谱仪设备状态 ====================

class VirtualSpectrometer:
    """虚拟 U-3900H 分光光度计，完全按照协议文档实现"""

    def __init__(self):
        self.device_id = "U-3900H-VIRTUAL-001"
        self.firmware_version = "1.0.0"

        self.field3 = "00"
        self.field4 = "00000000"

        # 扫描参数（默认值来自协议文档）
        self.scan_params = {
            "start_wavelength": 534.00,
            "end_wavelength": 200.00,
            "scan_speed": 300.0,
            "step": -1.0,
        }

        # 状态标志
        self.scanning = False
        self.baseline_running = False
        self.baseline_calibrated = False
        self.selftest_running = False

        # 基线数据
        self.baseline_data = {}

        # 扫描数据
        self.scan_data = []           # 当前扫描累积数据
        self.scan_complete_data = []  # 完成扫描后的数据

        self.current_wavelength = 534.00
        self.current_absorbance = 0.0
        self.scan_progress = 0.0

        # 随机光谱峰
        self._peaks = []

        # 事件队列（供服务端前端 HTTP 轮询）
        self._events = []
        self._events_lock = threading.Lock()
        self._event_id_counter = 0

        # 协议帧日志
        self.frame_logs = []
        self.frame_logs_lock = threading.Lock()

    # ---------- 事件系统 ----------
    def _push_event(self, event_type, data):
        with self._events_lock:
            self._event_id_counter += 1
            self._events.append({
                "id": self._event_id_counter,
                "type": event_type,
                "data": data,
                "time": time.time()
            })
            if len(self._events) > 500:
                self._events = self._events[-200:]

    def consume_events(self, after_id=0):
        with self._events_lock:
            if after_id == 0:
                return list(self._events)
            return [e for e in self._events if e["id"] > after_id]

    # ---------- 协议帧日志 ----------
    def log_frame(self, direction, payload_ascii, raw_hex=""):
        """记录协议帧通信日志（仅打印到终端，不打印 HTTP）"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        label = "TX →" if direction == "tx" else "RX ←"
        entry = {
            "time": timestamp,
            "direction": direction,
            "label": label,
            "payload": payload_ascii,
            "raw_hex": raw_hex,
        }
        with self.frame_logs_lock:
            self.frame_logs.append(entry)
            if len(self.frame_logs) > 200:
                self.frame_logs = self.frame_logs[-100:]
        self._push_event("frame_log", entry)
        # ★ 终端只打印协议帧
        print(f"[协议帧] {label} {payload_ascii}")
        if raw_hex:
            print(f"         HEX: {raw_hex}")

    def get_frame_logs(self, count=50):
        with self.frame_logs_lock:
            return self.frame_logs[-count:]

    # ---------- 自检与参数写入模拟 ----------
    def _simulate_selftest(self):
        """模拟真实仪器的自检过程（约 6 秒），完成后将状态置为就绪"""
        total_steps = 6
        for i in range(1, total_steps + 1):
            if not self.selftest_running:
                break
            print(f"[自检] 步骤 {i}/{total_steps}...")
            time.sleep(1.0)
        # 自检完成 → 置为就绪
        self.selftest_running = False
        self.field3 = "00"
        self.field4 = "00000000"
        self._push_event("selftest_complete", {"success": True})
        print("[自检] 完成，设备就绪 (field3=00, field4=00000000)")

    def _simulate_param_write(self):
        """模拟参数写入（约 1.5 秒），完成后将状态置为就绪"""
        time.sleep(1.5)
        self.field3 = "00"
        self.field4 = "00000200"
        self._push_event("params_updated", {"params": self.scan_params})
        print("[参数设置] 参数写入完成 (field4=00000200)")

    # ---------- 光谱生成 ----------
    def _generate_spectrum(self):
        self._peaks = []
        n_peaks = random.randint(3, 6)
        candidates = []
        attempts = 0
        while len(candidates) < n_peaks and attempts < 200:
            pos = random.uniform(200, 800)
            if all(abs(pos - c) >= 30 for c in candidates):
                candidates.append(pos)
            attempts += 1
        for pos in sorted(candidates):
            height = random.uniform(0.15, 1.5)
            sigma = random.uniform(8, 45)
            self._peaks.append((pos, height, sigma))
        print(f"[光谱生成] 随机峰: {[(p[0], round(p[1], 3), round(p[2], 1)) for p in self._peaks]}")

    def _calculate_absorbance(self, wavelength):
        wv = wavelength
        absorbance = 0.0
        for pos, height, sigma in self._peaks:
            absorbance += height * math.exp(-((wv - pos) ** 2) / (2 * sigma ** 2))
        if wv < 300:
            absorbance += 0.8 * math.exp(-(wv - 190.0) / 90.0)
        absorbance += 0.015 * math.sin(wv / 80.0 + random.random())
        absorbance += random.gauss(0, 0.0004)
        return max(absorbance, -0.003)

    @staticmethod
    def format_absorbance(value):
        """格式化为科学计数法，例如 1.2345e-02"""
        if value == 0:
            return "0.0000e+00"
        exp = int(math.floor(math.log10(abs(value))))
        mantissa = value / (10 ** exp)
        return f"{mantissa:.4f}e{exp:+03d}"

    def _calc_progress(self, current, start, end):
        if start == end:
            return 100.0
        return abs(current - start) / abs(end - start) * 100.0

    def clear_scan_data(self):
        self.scan_data = []
        self.scan_complete_data = []
        self.current_wavelength = self.scan_params["start_wavelength"]
        self.current_absorbance = 0.0
        self.scan_progress = 0.0

    def get_status_dict(self):
        return {
            "field3": self.field3,
            "field4": self.field4,
            "field3_desc": {"00": "空闲/完成", "01": "自检中", "02": "基线校准中"}.get(self.field3, "未知"),
            "field4_desc": {
                "00000000": "就绪/完成",
                "00000200": "Ready(可执行业务)",
                "00000A00": "Busy(忙碌)"
            }.get(self.field4, "未知"),
            "scanning": self.scanning,
            "baseline_running": self.baseline_running,
            "baseline_calibrated": self.baseline_calibrated,
            "selftest_running": self.selftest_running,
            "current_wavelength": self.current_wavelength,
            "current_absorbance": self.current_absorbance,
            "scan_progress": self.scan_progress,
            "scan_data_count": len(self.scan_data),
        }

    # ---------- 协议命令处理 ----------
    def handle_command(self, payload):
        """
        处理一条 U3900H 协议命令，返回响应 payload 字符串。
        完全按照协议文档实现。
        """
        tokens = payload.split()
        cmd = tokens[0] if tokens else ""

        if cmd == "00010002":
            # 5.2 读取 ID / 版本
            return f"00000600 00010002 {self.device_id} {self.firmware_version}"

        elif cmd == "00010810":
            # 5.3 初始化 / 读取大状态 — 模拟自检过程，设置 busy 状态
            self.selftest_running = True
            self.field3 = "01"
            self.field4 = "00000A00"
            self._push_event("selftest_started", {})
            print("[自检] 初始化启动，进入 busy 状态...")
            threading.Thread(target=self._simulate_selftest, daemon=True).start()
            return "00000600 00010810 01 00000A00"

        elif cmd == "00010300":
            # 5.4 设置 / 初始化模式 — 返回当前状态（自检中则返回 busy）
            return f"00000600 00010300 {self.field3} {self.field4}"

        elif cmd == "00010100":
            # 5.5 方法参数设置 — 模拟参数写入过程，短暂进入 busy 状态
            numeric_vals = []
            for t in tokens[1:]:
                try:
                    numeric_vals.append(float(t))
                except ValueError:
                    pass
            if len(numeric_vals) >= 3:
                self.scan_params["scan_speed"] = numeric_vals[-3]
                self.scan_params["start_wavelength"] = numeric_vals[-2]
                self.scan_params["end_wavelength"] = numeric_vals[-1]
                self.scan_params["step"] = -1.0 if numeric_vals[-2] > numeric_vals[-1] else 1.0
                print(f"[参数设置] 起始={self.scan_params['start_wavelength']:.2f}nm, "
                      f"结束={self.scan_params['end_wavelength']:.2f}nm, "
                      f"速度={self.scan_params['scan_speed']:.1f}nm/min")
            self.field3 = "00"
            self.field4 = "00000A00"
            self._push_event("params_updated", {"params": self.scan_params})
            # 短暂延迟后置为就绪
            threading.Thread(target=self._simulate_param_write, daemon=True).start()
            return "00000600 00010100 00 00000A00"

        elif cmd == "00010800":
            # 5.6 状态轮询
            response = f"00000600 00010800 {self.field3} {self.field4}"
            if self.scan_data:
                last = self.scan_data[-1]
                response += f" {last['wavelength']:.4f} {self.format_absorbance(last['absorbance'])}"
            return response

        elif cmd == "00010323":
            # 5.7 基线校准  命令: 00010323  1 (两个空格 + 1)
            if self.baseline_running:
                return f"00000600 00010323 02 00000A00"
            self.baseline_running = True
            self.field3 = "02"
            self.field4 = "00000A00"
            self._push_event("baseline_started", {"message": "基线校准已启动"})

            def _do_baseline():
                start_wv = self.scan_params["start_wavelength"]
                end_wv = self.scan_params["end_wavelength"]
                step = -1.0 if start_wv > end_wv else 1.0
                current = start_wv
                while True:
                    if current > max(start_wv, end_wv) + 0.1 or current < min(start_wv, end_wv) - 0.1:
                        break
                    self.baseline_data[round(current, 1)] = random.gauss(0, 0.0003)
                    current += step
                    time.sleep(0.003)
                self.field3 = "00"
                self.field4 = "00000200"
                self.baseline_running = False
                self.baseline_calibrated = True
                self._push_event("baseline_complete", {"success": True, "message": "基线校准完成"})
                print("[基线校准] 完成")

            threading.Thread(target=_do_baseline, daemon=True).start()
            return "00000600 00010323 02 00000A00"

        elif cmd == "00010500":
            # 5.8 开始扫描测量
            self.clear_scan_data()
            self.scanning = True
            self._generate_spectrum()
            self.field3 = "00"
            self.field4 = "00000200"
            self._push_event("scan_started", {"message": "扫描已开始"})
            print("[扫描] 开始")
            return "00000600 00010500 00 00000200"

        elif cmd == "00010801":
            # 5.9 设置波长（单点测量）  命令: 00010801   600.0000 (三个空格)
            if len(tokens) >= 2:
                try:
                    wv = float(tokens[1])
                except ValueError:
                    wv = 600.0
            else:
                wv = 600.0

            absorbance = self._calculate_absorbance(wv)
            if self.baseline_calibrated:
                baseline_val = self.baseline_data.get(round(wv, 1), 0.0)
                absorbance -= baseline_val

            point = {"wavelength": round(wv, 2), "absorbance": absorbance}
            self.scan_data.append(point)
            self.current_wavelength = round(wv, 2)
            self.current_absorbance = absorbance

            start = self.scan_params["start_wavelength"]
            end = self.scan_params["end_wavelength"]
            self.scan_progress = self._calc_progress(wv, start, end)

            self._push_event("scan_update", {
                "wavelength": round(wv, 2),
                "absorbance": absorbance,
                "progress": self.scan_progress,
            })

            return f"00000600 00010801 00 00000200 {wv:.4f} {self.format_absorbance(absorbance)}"

        elif cmd == "00010302":
            # 5.10 结束扫描测量  命令: 00010302  0  0
            was_scanning = self.scanning
            self.scanning = False
            self.field3 = "00"
            self.field4 = "00000000"
            if was_scanning and self.scan_data:
                self.scan_complete_data = [{"w": p["wavelength"], "a": p["absorbance"]} for p in self.scan_data]
                self._push_event("scan_complete", {
                    "total_points": len(self.scan_complete_data),
                    "data": self.scan_complete_data,
                })
                print(f"[扫描] 完成，共 {len(self.scan_complete_data)} 个数据点")
            return "00000600 00010302 00 00000000"

        else:
            # 未知命令
            return f"00001500 {cmd} 00 00000A00"


# 全局虚拟光谱仪实例
spectrometer = VirtualSpectrometer()


# ==================== TCP Socket 协议服务器 ====================

class TCPSpectrometerServer:
    """TCP 服务器，使用 U3900H 协议帧与第三方 Socket 客户端通信"""

    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.client_sockets = []
        self.client_buffers = {}  # socket -> bytearray

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.setblocking(False)
        self.running = True
        print(f"[TCP] U3900H 协议端口已启动: {self.host}:{self.port}")

        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        while self.running:
            try:
                read_sockets = [self.server_socket] + self.client_sockets
                readable, _, exceptional = select.select(read_sockets, [], read_sockets, 0.5)

                for s in readable:
                    if s is self.server_socket:
                        client_sock, addr = self.server_socket.accept()
                        client_sock.setblocking(False)
                        self.client_sockets.append(client_sock)
                        self.client_buffers[client_sock] = bytearray()
                        print(f"[TCP] 客户端已连接: {addr[0]}:{addr[1]}")
                    else:
                        try:
                            data = s.recv(4096)
                            if data:
                                self.client_buffers[s] += data
                                self._process_buffer(s)
                            else:
                                self._disconnect_client(s)
                        except (ConnectionResetError, ConnectionAbortedError, OSError):
                            self._disconnect_client(s)

                for s in exceptional:
                    self._disconnect_client(s)

            except Exception as e:
                if self.running:
                    print(f"[TCP] 异常: {e}")
                time.sleep(0.1)

    def _process_buffer(self, client_sock):
        buf = self.client_buffers[client_sock]
        while True:
            frame_bytes = bytes(buf)
            payload_str, consumed = decode_frame(frame_bytes)
            if consumed == 0:
                break
            if payload_str is None:
                del buf[:consumed]
                continue

            del buf[:consumed]

            # 记录接收帧
            full_frame_hex = encode_frame(payload_str).hex(" ").upper()
            spectrometer.log_frame("rx", payload_str, full_frame_hex)

            # 处理命令并发送响应
            response_payload = spectrometer.handle_command(payload_str)
            try:
                resp_frame = encode_frame(response_payload)
                resp_hex = resp_frame.hex(" ").upper()
                spectrometer.log_frame("tx", response_payload, resp_hex)
                client_sock.sendall(resp_frame)
            except Exception as e:
                print(f"[TCP] 发送失败: {e}")
                self._disconnect_client(client_sock)
                break

    def _disconnect_client(self, s):
        if s in self.client_sockets:
            self.client_sockets.remove(s)
        if s in self.client_buffers:
            del self.client_buffers[s]
        try:
            s.close()
        except Exception:
            pass
        print("[TCP] 客户端已断开")

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        for s in list(self.client_sockets):
            try:
                s.close()
            except Exception:
                pass


# ==================== Flask HTTP 路由（服务端前端专用） ====================

@app.route("/")
def index():
    return render_template("server_dashboard.html")


@app.route("/api/status")
def api_status():
    return jsonify(spectrometer.get_status_dict())


@app.route("/api/scan_data")
def api_scan_data():
    return jsonify({
        "data": [{"w": p["wavelength"], "a": p["absorbance"]} for p in spectrometer.scan_data],
        "complete_data": spectrometer.scan_complete_data,
        "params": spectrometer.scan_params,
        "current": {
            "wavelength": spectrometer.current_wavelength,
            "absorbance": spectrometer.current_absorbance,
            "progress": spectrometer.scan_progress,
        }
    })


@app.route("/api/events")
def api_events():
    after_id = request.args.get("after_id", 0, type=int)
    events = spectrometer.consume_events(after_id)
    return jsonify({
        "events": events,
        "latest_id": events[-1]["id"] if events else after_id,
        "status": spectrometer.get_status_dict()
    })


@app.route("/api/frame_logs")
def api_frame_logs():
    count = request.args.get("count", 50, type=int)
    return jsonify({"logs": spectrometer.get_frame_logs(count)})


@app.route("/api/set_params", methods=["POST"])
def api_set_params():
    data = request.json or {}
    if "start_wavelength" in data:
        spectrometer.scan_params["start_wavelength"] = float(data["start_wavelength"])
    if "end_wavelength" in data:
        spectrometer.scan_params["end_wavelength"] = float(data["end_wavelength"])
    if "scan_speed" in data:
        spectrometer.scan_params["scan_speed"] = float(data["scan_speed"])
    if "step" in data:
        spectrometer.scan_params["step"] = float(data["step"])
    return jsonify({"success": True, "params": spectrometer.scan_params})


# ==================== 启动入口 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("  U-3900H 虚拟光谱仪服务器")
    print(f"  管理页面 (HTTP):      http://localhost:5000")
    print(f"  U3900H 协议端口 (TCP): 0.0.0.0:9000")
    print("=" * 60)

    # 启动 TCP 协议服务器（供第三方 Socket 客户端连接）
    tcp_server = TCPSpectrometerServer(host="0.0.0.0", port=9000)
    tcp_server.start()

    # 启动 Flask HTTP 服务（供服务端前端使用）
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
