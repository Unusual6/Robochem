#!/usr/bin/env python3
"""
光谱仪客户端程序 (Spectrometer Client)
- Flask HTTP (端口 5001): 客户端前端管理页面
- TCP Socket 连接服务端 9000 端口，使用 U3900H 协议帧通信
  仅打印 U3900H 协议帧交互，不打印 HTTP 请求
"""

import os
import struct
import time
import math
import threading
import logging
import socket
import webbrowser
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# ==================== 抑制 Flask HTTP 请求日志 ====================
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('flask.app').setLevel(logging.ERROR)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config["SECRET_KEY"] = "u3900h_client_secret"
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
    """
    if len(data) < 7:
        return None, 0
    if data[0] != STX:
        for i in range(1, len(data)):
            if data[i] == STX:
                return None, i
        return None, len(data)
    length = struct.unpack(">I", data[1:5])[0]
    frame_len = 7 + length
    if len(data) < frame_len:
        return None, 0
    if data[5 + length] != ETX:
        return None, 1
    payload_bytes = data[5:5 + length]
    payload_str = payload_bytes.decode("ascii", errors="replace")
    return payload_str, frame_len


def parse_status_response(payload_str):
    """
    解析状态响应，提取 field3, field4, 波长, 吸光度。
    响应格式: 00000600 00010800 <field3> <field4> [波长] [吸光度]
    """
    tokens = payload_str.split()
    result = {"raw": payload_str, "tokens": tokens}
    if len(tokens) >= 4:
        result["field3"] = tokens[2]
        result["field4"] = tokens[3]
    if len(tokens) >= 5:
        try:
            result["wavelength"] = float(tokens[4])
        except ValueError:
            pass
    if len(tokens) >= 6:
        result["absorbance_raw"] = tokens[5]
        try:
            result["absorbance"] = float(tokens[5])
        except ValueError:
            pass
    return result


def parse_scan_response(payload_str):
    """
    解析扫描点响应，提取波长和吸光度。
    响应格式: 00000600 00010801 00 00000200 <波长> <吸光度>
    """
    tokens = payload_str.split()
    result = {"raw": payload_str, "tokens": tokens}
    if len(tokens) >= 5:
        try:
            result["wavelength"] = float(tokens[4])
        except ValueError:
            pass
    if len(tokens) >= 6:
        result["absorbance_raw"] = tokens[5]
        try:
            result["absorbance"] = float(tokens[5])
        except ValueError:
            pass
    return result


# ==================== TCP 协议客户端 ====================

class SpectrometerTCPClient:
    """通过 TCP Socket 使用 U3900H 协议与虚拟光谱仪通信"""

    def __init__(self, host="localhost", port=9000):
        self.host = host
        self.port = port
        self.sock = None
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.connected = False

        # 当前状态
        self.status = {
            "field3": "00",
            "field4": "00000000",
            "current_wavelength": 534.00,
            "current_absorbance": 0.0,
        }
        self.scan_params = {
            "start_wavelength": 534.00,
            "end_wavelength": 200.00,
            "scan_speed": 300.0,
            "step": -1.0,
        }
        self.scan_data = []
        self.scan_complete_data = []
        self.scan_progress = 0.0
        self.scanning = False
        self.baseline_calibrated = False
        self.baseline_running = False

        # 协议帧日志
        self.frame_logs = []
        self.frame_logs_lock = threading.Lock()

        # 事件队列（供前端 HTTP 轮询）
        self._events = []
        self._events_lock = threading.Lock()
        self._event_id_counter = 0

    # ---------- 事件系统 ----------
    def _push_event(self, event_type, data):
        with self._events_lock:
            self._event_id_counter += 1
            self._events.append({
                "id": self._event_id_counter,
                "type": event_type,
                "data": data,
                "time": time.time(),
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
        direction_full = "TX → 服务器" if direction == "tx" else "RX ← 服务器"
        print(f"[协议帧-客户端] {direction_full}: {payload_ascii}")
        if raw_hex:
            print(f"                 HEX: {raw_hex}")

    def get_frame_logs(self, count=50):
        with self.frame_logs_lock:
            return self.frame_logs[-count:]

    # ---------- 连接管理 ----------
    def connect(self):
        """建立 TCP 连接"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)
            self.connected = True
            print(f"[客户端] 已连接虚拟光谱仪 {self.host}:{self.port}")
            self._push_event("connected", {"host": self.host, "port": self.port})
            # 启动接收线程
            threading.Thread(target=self._recv_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"[客户端] 连接失败: {e}")
            self._push_event("error", {"message": f"连接失败: {e}"})
            return False

    def disconnect(self):
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.buffer = bytearray()
        print("[客户端] 已断开连接")
        self._push_event("disconnected", {})

    def _recv_loop(self):
        """后台接收线程，处理来自服务端的异步通知"""
        while self.connected:
            try:
                data = self.sock.recv(4096)
                if not data:
                    print("[客户端] 服务器断开连接")
                    self.disconnect()
                    break
                self.buffer += data
                self._process_buffer()
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                if self.connected:
                    print(f"[客户端] 接收异常: {e}")
                    self.disconnect()
                break
            except Exception as e:
                if self.connected:
                    print(f"[客户端] 接收错误: {e}")
                break

    def _process_buffer(self):
        while True:
            frame_bytes = bytes(self.buffer)
            payload_str, consumed = decode_frame(frame_bytes)
            if consumed == 0:
                break
            if payload_str is None:
                del self.buffer[:consumed]
                continue
            del self.buffer[:consumed]

            # 记录接收帧
            full_frame_hex = encode_frame(payload_str).hex(" ").upper()
            self.log_frame("rx", payload_str, full_frame_hex)

            # 解析并更新状态
            self._handle_response(payload_str)

    def _handle_response(self, payload_str):
        """解析服务端响应，更新本地状态"""
        tokens = payload_str.split()
        if len(tokens) < 2:
            return

        cmd = tokens[1] if len(tokens) > 1 else ""

        if cmd == "00010800":
            parsed = parse_status_response(payload_str)
            self.status["field3"] = parsed.get("field3", self.status["field3"])
            self.status["field4"] = parsed.get("field4", self.status["field4"])
            if "wavelength" in parsed:
                self.status["current_wavelength"] = parsed["wavelength"]
            if "absorbance" in parsed:
                self.status["current_absorbance"] = parsed["absorbance"]

        elif cmd == "00010801":
            parsed = parse_scan_response(payload_str)
            wv = parsed.get("wavelength")
            ab = parsed.get("absorbance")
            if wv is not None and ab is not None:
                point = {"wavelength": round(wv, 2), "absorbance": ab}
                self.scan_data.append(point)
                self.status["current_wavelength"] = round(wv, 2)
                self.status["current_absorbance"] = ab
                # 计算进度
                start = self.scan_params["start_wavelength"]
                end = self.scan_params["end_wavelength"]
                if start != end:
                    self.scan_progress = abs(wv - start) / abs(end - start) * 100
                self._push_event("scan_update", {
                    "wavelength": round(wv, 2),
                    "absorbance": ab,
                    "progress": self.scan_progress,
                })

        elif cmd == "00010302":
            self.scanning = False
            if self.scan_data:
                self.scan_complete_data = [{"w": p["wavelength"], "a": p["absorbance"]} for p in self.scan_data]
                self._push_event("scan_complete", {
                    "total_points": len(self.scan_complete_data),
                    "data": self.scan_complete_data,
                })

        elif cmd == "00010100":
            self._push_event("params_updated", {"params": self.scan_params})

        elif cmd == "00010323":
            parsed = parse_status_response(payload_str)
            if parsed.get("field3") == "02":
                self.baseline_running = True
                self._push_event("baseline_started", {})
            else:
                self.baseline_running = False
                self.baseline_calibrated = True
                self._push_event("baseline_complete", {"success": True})

    # ---------- 协议命令发送 ----------
    def _send_command(self, payload_ascii):
        """
        发送协议帧（仅发送，不等待响应）。
        响应由后台 _recv_loop 统一接收、解码并更新 self.status 和事件队列，
        各业务方法通过轮询状态/事件来判断操作完成。
        """
        if not self.connected or not self.sock:
            return False
        with self.lock:
            try:
                frame = encode_frame(payload_ascii)
                frame_hex = frame.hex(" ").upper()
                self.log_frame("tx", payload_ascii, frame_hex)
                self.sock.sendall(frame)
                return True
            except Exception as e:
                print(f"[客户端] 发送失败: {e}")
                self._push_event("error", {"message": f"通讯异常: {e}"})
                return False

    # ---------- 等待状态就绪 ----------
    def _wait_ready(self, timeout=5.0, poll_interval=0.3):
        """
        轮询直到设备就绪（field3=00, field4=00000000 或 00000200）。
        强制先发送一轮状态查询再判断，避免初始默认值导致的假就绪。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            # 发送状态查询帧，响应由 _recv_loop 更新 self.status
            self._send_command("00010800")
            time.sleep(poll_interval)
            if (self.status.get("field3") == "00"
                    and self.status.get("field4") in ["00000000", "00000200"]):
                return True
        return False

    # ---------- 业务方法 ----------
    def do_selftest(self):
        """
        执行自检流程，严格按协议文档 6.1 节：
          00010002 → 00010810 → 00010300
          → 轮询至 field3=00, field4=00000000
          → 00010100 (方法参数)
          → 轮询至 field3=00, field4∈{00000000, 00000200}
        响应均由后台 _recv_loop 统一更新 self.status，通过 _wait_ready 轮询判断。
        """
        self._push_event("selftest_started", {})
        print("[客户端] 自检开始...")

        # ---- 阶段1: 自检命令序列 ----
        self._send_command("00010002")  # 读取设备ID
        time.sleep(0.5)
        self._send_command("00010810")  # 初始化
        time.sleep(0.5)
        self._send_command("00010300")  # 模式初始化
        print("[客户端] 自检命令已发送，轮询等待就绪 (field3=00, field4=00000000)...")

        # 轮询等待自检就绪
        if self._wait_ready(timeout=10.0):
            print("[客户端] 自检第一阶段完成 — 设备已就绪")
        else:
            print("[客户端] 自检第一阶段 — 状态轮询超时，继续尝试...")

        # ---- 阶段2: 发送方法参数 ----
        start = self.scan_params["start_wavelength"]
        end = self.scan_params["end_wavelength"]
        speed = self.scan_params["scan_speed"]
        self.scan_params["step"] = -1.0 if start > end else 1.0
        cmd = f"00010100   17  3  0  0  1   {speed:.1f}   {start:.2f}   {end:.2f}  0   1.0  1   500  0   325.00  1  1  1  1     0.00  0  0   340.00    120.0"
        print(f"[客户端] 自检 — 发送方法参数: 起始={start:.2f}nm, 结束={end:.2f}nm, 速度={speed:.1f}nm/min")
        self._send_command(cmd)

        # 轮询等待方法参数生效
        if self._wait_ready(timeout=10.0):
            print("[客户端] 自检完成 — 方法参数已生效，设备就绪")
        else:
            print("[客户端] 自检完成 — 参数轮询超时，强制完成")

        self._push_event("selftest_complete", {"success": True})
        print("[客户端] 自检完成")

    def do_set_params(self, start_wv=None, end_wv=None, scan_speed=None):
        """设置扫描参数"""
        if start_wv is not None:
            self.scan_params["start_wavelength"] = float(start_wv)
        if end_wv is not None:
            self.scan_params["end_wavelength"] = float(end_wv)
        if scan_speed is not None:
            self.scan_params["scan_speed"] = float(scan_speed)

        start = self.scan_params["start_wavelength"]
        end = self.scan_params["end_wavelength"]
        speed = self.scan_params["scan_speed"]
        self.scan_params["step"] = -1.0 if start > end else 1.0

        # 按照协议文档 5.5 节格式构造参数命令
        cmd = f"00010100   17  3  0  0  1   {speed:.1f}   {start:.2f}   {end:.2f}  0   1.0  1   500  0   325.00  1  1  1  1     0.00  0  0   340.00    120.0"
        print(f"[客户端] 设置参数: 起始={start:.2f}nm, 结束={end:.2f}nm, 速度={speed:.1f}nm/min")
        self._send_command(cmd)
        # 参数设置完成后推送事件通知前端恢复按钮
        self._push_event("params_updated", {"params": dict(self.scan_params)})

    def do_baseline_calibrate(self):
        """执行基线校准：发送校准命令后通过协议帧轮询服务端状态直到就绪"""
        self.baseline_running = True
        self._push_event("baseline_started", {})
        print("[客户端] 基线校准开始...")

        # 确认就绪
        if not self._wait_ready(timeout=5.0):
            print("[客户端] 基线校准 — 设备未就绪，继续尝试...")

        # 发送基线校准命令
        self._send_command("00010323  1")

        # 轮询等待校准完成（field3=00 且 field4 就绪）
        if self._wait_ready(timeout=30.0, poll_interval=0.5):
            print("[客户端] 基线校准完成 — 设备已就绪")
        else:
            print("[客户端] 基线校准 — 状态轮询超时，强制完成")

        self.baseline_running = False
        self.baseline_calibrated = True
        self._push_event("baseline_complete", {"success": True})
        print("[客户端] 基线校准完成")

    def do_start_scan(self):
        """开始扫描测量：发送命令后逐波长测量，响应由后台 _recv_loop 处理"""
        self.scan_data = []
        self.scan_complete_data = []
        self.scan_progress = 0.0
        self.scanning = True
        self._push_event("scan_started", {})
        print("[客户端] 扫描开始...")

        # 发送开始扫描命令
        self._send_command("00010500")
        time.sleep(0.3)

        # 按步进发送波长测量命令
        start = self.scan_params["start_wavelength"]
        end = self.scan_params["end_wavelength"]
        step = self.scan_params["step"]

        total_steps = max(1, int(abs(end - start) / abs(step)) + 1)
        current = start

        for i in range(min(total_steps, 300)):
            if step > 0 and current > end:
                break
            if step < 0 and current < end:
                break

            wv = round(current, 4)
            wv_str = f"{wv:.4f}"
            self._send_command(f"00010801   {wv_str}")
            time.sleep(0.05)
            current += step

        # 发送结束扫描命令
        self._send_command("00010302  0  0")
        time.sleep(0.2)

        # 从 self.scan_data（由 _recv_loop 填充）汇总扫描结果
        self.scanning = False
        self.scan_complete_data = [{"w": p["wavelength"], "a": p["absorbance"]} for p in self.scan_data]
        self.scan_progress = 100.0
        self._push_event("scan_complete", {
            "total_points": len(self.scan_complete_data),
            "data": self.scan_complete_data,
        })
        print(f"[客户端] 扫描完成，共 {len(self.scan_complete_data)} 个数据点")

    def do_poll_status(self):
        """轮询设备状态"""
        self._send_command("00010800")


# ==================== 全局客户端实例 ====================

client = SpectrometerTCPClient(host="localhost", port=9000)


# ==================== Flask HTTP 路由（客户端前端专用） ====================

@app.route("/")
def index():
    return render_template("client_dashboard.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "connected": client.connected,
        "scanning": client.scanning,
        "baseline_running": client.baseline_running,
        "baseline_calibrated": client.baseline_calibrated,
        "scan_progress": client.scan_progress,
        "status": client.status,
        "scan_params": client.scan_params,
        "scan_data_count": len(client.scan_data),
    })


@app.route("/api/scan_data")
def api_scan_data():
    return jsonify({
        "data": client.scan_data,
        "complete_data": client.scan_complete_data,
        "params": client.scan_params,
        "current": {
            "wavelength": client.status.get("current_wavelength", 0),
            "absorbance": client.status.get("current_absorbance", 0),
            "progress": client.scan_progress,
        }
    })


@app.route("/api/events")
def api_events():
    after_id = request.args.get("after_id", 0, type=int)
    events = client.consume_events(after_id)
    return jsonify({
        "events": events,
        "latest_id": events[-1]["id"] if events else after_id,
        "connected": client.connected,
        "scanning": client.scanning,
        "scan_progress": client.scan_progress,
    })


@app.route("/api/frame_logs")
def api_frame_logs():
    count = request.args.get("count", 50, type=int)
    return jsonify({"logs": client.get_frame_logs(count)})


@app.route("/api/connect", methods=["POST"])
def api_connect():
    success = client.connect()
    return jsonify({"success": success, "connected": client.connected})


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    client.disconnect()
    return jsonify({"success": True, "connected": False})


@app.route("/api/selftest", methods=["POST"])
def api_selftest():
    threading.Thread(target=client.do_selftest, daemon=True).start()
    return jsonify({"success": True, "message": "自检已启动"})


@app.route("/api/set_params", methods=["POST"])
def api_set_params():
    data = request.json or {}
    start = data.get("start_wavelength")
    end = data.get("end_wavelength")
    speed = data.get("scan_speed")
    threading.Thread(target=client.do_set_params, args=(start, end, speed), daemon=True).start()
    return jsonify({"success": True, "params": client.scan_params})


@app.route("/api/baseline", methods=["POST"])
def api_baseline():
    threading.Thread(target=client.do_baseline_calibrate, daemon=True).start()
    return jsonify({"success": True, "message": "基线校准已启动"})


@app.route("/api/start_scan", methods=["POST"])
def api_start_scan():
    threading.Thread(target=client.do_start_scan, daemon=True).start()
    return jsonify({"success": True, "message": "扫描已启动"})


@app.route("/api/poll_status", methods=["POST"])
def api_poll_status():
    client.do_poll_status()
    return jsonify({"success": True})


# ==================== 启动入口 ====================

def auto_open_browser():
    import time as _time
    _time.sleep(1.5)
    webbrowser.open("http://localhost:5001")


if __name__ == "__main__":
    print("=" * 60)
    print("  U-3900H 光谱仪客户端")
    print(f"  客户端前端 (HTTP):  http://localhost:5001")
    print(f"  协议连接目标 (TCP):  localhost:9000")
    print("=" * 60)

    threading.Thread(target=auto_open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
