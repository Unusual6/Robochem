"""
Author: Robochem U3900H Integration

Descr: Device driver for Hitachi U-3900H UV-Vis Spectrometer.
       Communicates via TCP using the U3900H binary protocol (STX/ETX framing).
       Inherits BaseDevice to integrate with the OmniPlatypus platform.
"""

import socket
import struct
import threading
import time
from typing import Any

import pandas as pd

from omniplatypus.devices.base.device import (
    BaseDevice,
    DeviceParameter,
    ParameterAccess,
    ParameterCachingPolicy,
)


# ==================== U3900H Protocol Constants ====================

STX, ETX = 0x02, 0x03


def _calc_bcc(length4: bytes, payload: bytes) -> int:
    x = 0
    for v in length4 + payload + bytes([ETX]):
        x ^= v
    return x ^ STX


def _encode_frame(payload_ascii: str) -> bytes:
    payload = payload_ascii.encode("ascii")
    length4 = len(payload).to_bytes(4, "big")
    bcc = _calc_bcc(length4, payload)
    return bytes([STX]) + length4 + payload + bytes([ETX, bcc])


def _decode_frame(data: bytes):
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


# ==================== U3900HSpectrometer Driver ====================

class U3900HSpectrometer(BaseDevice):
    """
    Handles communication with Hitachi U-3900H UV-Vis Spectrometer.

    Usage:
        1. Connect via platform: platform builds this device automatically
        2. Set parameters: self['start_wavelength'] = 500.0
        3. Run baseline: self['baseline_calibrate'] = True
        4. Start scan: self['start_scan'] = True
        5. Read data: data = self['data']

    Parameters:
        start_wavelength  - Scan start wavelength (nm), range 190-1100
        end_wavelength    - Scan end wavelength (nm), range 190-1100
        scan_speed        - Scan speed (nm/min), range 1-3000
        data              - Spectral data (pd.DataFrame)
        start_scan        - Set True to trigger scan acquisition
        baseline_calibrate - Set True to trigger baseline calibration
        selftest           - Set True to trigger self-test
        status             - Current device status dict
        scan_progress      - Scan progress (0-100%)
    """

    def __init__(self):
        BaseDevice.__init__(self)
        self.generic_name = "U-3900H UV-Vis Spectrometer"

        self._sock = None
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._connected = False
        self._recv_thread = None
        self._host = None
        self._port = None

        # Internal state
        self._internal_scan_data = []
        self._internal_scan_complete_data = []
        self._internal_scan_progress = 0.0
        self._internal_scanning = False
        self._internal_baseline_calibrated = False
        self._internal_baseline_running = False
        self._internal_status = {
            "field3": "00",
            "field4": "00000000",
            "current_wavelength": 534.00,
            "current_absorbance": 0.0,
        }

        # ---- Device Parameters ----

        parameter = DeviceParameter(
            name="start_wavelength",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_id=401,
        )
        parameter.description = "Scan start wavelength"
        parameter.units = "nm"
        parameter.min_value = 190.0
        parameter.max_value = 1100.0
        parameter.caching_policy = ParameterCachingPolicy.ALWAYS
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="end_wavelength",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_id=402,
        )
        parameter.description = "Scan end wavelength"
        parameter.units = "nm"
        parameter.min_value = 190.0
        parameter.max_value = 1100.0
        parameter.caching_policy = ParameterCachingPolicy.ALWAYS
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="scan_speed",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_id=403,
        )
        parameter.description = "Scan speed"
        parameter.units = "nm/min"
        parameter.min_value = 1.0
        parameter.max_value = 3000.0
        parameter.caching_policy = ParameterCachingPolicy.ALWAYS
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="data",
            access_level=ParameterAccess.R,
            value_type=pd.DataFrame,
            internal_id=404,
        )
        parameter.description = "Spectral scan data (wavelength, absorbance)"
        parameter.caching_policy = ParameterCachingPolicy.NEVER
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="start_scan",
            access_level=ParameterAccess.RW,
            value_type=bool,
            internal_id=405,
        )
        parameter.description = "Start scan acquisition. Set to True to trigger."
        parameter.caching_policy = ParameterCachingPolicy.ALWAYS
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="baseline_calibrate",
            access_level=ParameterAccess.RW,
            value_type=bool,
            internal_id=406,
        )
        parameter.description = "Trigger baseline calibration. Set to True to trigger."
        parameter.caching_policy = ParameterCachingPolicy.ALWAYS
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="selftest",
            access_level=ParameterAccess.RW,
            value_type=bool,
            internal_id=407,
        )
        parameter.description = "Trigger device self-test. Set to True to trigger."
        parameter.caching_policy = ParameterCachingPolicy.ALWAYS
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="status",
            access_level=ParameterAccess.R,
            value_type=dict,
            internal_id=408,
        )
        parameter.description = "Current device status (wavelength, absorbance, progress)"
        parameter.caching_policy = ParameterCachingPolicy.NEVER
        self.add_parameter(parameter)

        parameter = DeviceParameter(
            name="scan_progress",
            access_level=ParameterAccess.R,
            value_type=float,
            internal_id=409,
        )
        parameter.description = "Scan progress percentage (0-100)"
        parameter.caching_policy = ParameterCachingPolicy.NEVER
        self.add_parameter(parameter)

    # ========== Connection Management ==========

    def open(self, host: str, port: int):
        """Establish TCP connection to the U3900H spectrometer."""
        self._host = host
        self._port = port
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5)
            self._sock.connect((host, port))
            self._sock.settimeout(None)
            self._connected = True
            self.log(f"Connected to U3900H at {host}:{port}")
            self._recv_thread = threading.Thread(
                target=self._recv_loop, daemon=True
            )
            self._recv_thread.start()
        except Exception as e:
            self._connected = False
            self._sock = None
            self.log(f"Failed to connect to U3900H: {e}", level="error")
            raise ConnectionError(f"U3900H connection failed: {e}")

    def close(self):
        """Close TCP connection."""
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = bytearray()

    def is_open(self) -> bool:
        return self._connected and self._sock is not None

    # ========== Background Receive Loop ==========

    def _recv_loop(self):
        """Background thread to receive and process frames from the spectrometer."""
        while self._connected:
            try:
                data = self._sock.recv(4096)
                if not data:
                    self.log("U3900H server disconnected")
                    self.close()
                    break
                self._buffer += data
                self._process_buffer()
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                if self._connected:
                    self.log(f"U3900H receive error: {e}", level="error")
                    self.close()
                break
            except Exception as e:
                if self._connected:
                    self.log(f"U3900H receive error: {e}", level="error")
                break

    def _process_buffer(self):
        while True:
            frame_bytes = bytes(self._buffer)
            payload_str, consumed = _decode_frame(frame_bytes)
            if consumed == 0:
                break
            if payload_str is None:
                del self._buffer[:consumed]
                continue
            del self._buffer[:consumed]
            self._handle_response(payload_str)

    def _handle_response(self, payload_str: str):
        """Parse spectrometer response and update internal state."""
        tokens = payload_str.split()
        if len(tokens) < 2:
            return

        cmd = tokens[1] if len(tokens) > 1 else ""

        if cmd == "00010800":
            # Status response: wavelength, absorbance
            if len(tokens) >= 3:
                self._internal_status["field3"] = tokens[2]
            if len(tokens) >= 4:
                self._internal_status["field4"] = tokens[3]
            if len(tokens) >= 5:
                try:
                    self._internal_status["current_wavelength"] = float(tokens[4])
                except ValueError:
                    pass
            if len(tokens) >= 6:
                try:
                    self._internal_status["current_absorbance"] = float(tokens[5])
                except ValueError:
                    pass

        elif cmd == "00010801":
            # Scan data point response
            if len(tokens) >= 5:
                try:
                    wv = float(tokens[4])
                    self._internal_status["current_wavelength"] = wv
                except ValueError:
                    wv = None
            else:
                wv = None
            if len(tokens) >= 6:
                try:
                    ab = float(tokens[5])
                    self._internal_status["current_absorbance"] = ab
                except ValueError:
                    ab = None
            else:
                ab = None
            if wv is not None and ab is not None:
                self._internal_scan_data.append(
                    {"wavelength": round(wv, 2), "absorbance": ab}
                )
                # Update progress
                start = self._scan_start_wv or 534.0
                end = self._scan_end_wv or 200.0
                if start != end:
                    self._internal_scan_progress = (
                        abs(wv - start) / abs(end - start) * 100
                    )

        elif cmd == "00010302":
            # Scan complete
            self._internal_scanning = False
            if self._internal_scan_data:
                self._internal_scan_complete_data = [
                    {"w": p["wavelength"], "a": p["absorbance"]}
                    for p in self._internal_scan_data
                ]
            self._internal_scan_progress = 100.0

        elif cmd == "00010323":
            # Baseline calibration response
            if len(tokens) >= 3 and tokens[2] == "02":
                self._internal_baseline_running = True
            else:
                self._internal_baseline_running = False
                self._internal_baseline_calibrated = True

    # ========== Protocol Command Sending ==========

    def _send_frame(self, payload_ascii: str) -> bool:
        """Send a protocol frame to the spectrometer."""
        if not self.is_open():
            return False
        with self._lock:
            try:
                frame = _encode_frame(payload_ascii)
                self._sock.sendall(frame)
                return True
            except Exception as e:
                self.log(f"U3900H send failed: {e}", level="error")
                return False

    def _wait_ready(self, timeout: float = 10.0, poll_interval: float = 0.3) -> bool:
        """Poll until device is ready (field3=00, field4 in 00000000 or 00000200)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._send_frame("00010800")
            time.sleep(poll_interval)
            if (
                self._internal_status.get("field3") == "00"
                and self._internal_status.get("field4") in ["00000000", "00000200"]
            ):
                return True
        return False

    # ========== Core BaseDevice Methods ==========

    def _write(self, parameter: DeviceParameter, value: Any) -> None:
        """Write a parameter value to the device."""
        name = parameter.name

        if name == "start_wavelength":
            self._scan_start_wv = float(value)
            self.log(f"Start wavelength set to {value} nm")

        elif name == "end_wavelength":
            self._scan_end_wv = float(value)
            self.log(f"End wavelength set to {value} nm")

        elif name == "scan_speed":
            self._scan_speed = float(value)
            self.log(f"Scan speed set to {value} nm/min")

        elif name == "start_scan" and value is True:
            self._do_scan(parameter)

        elif name == "baseline_calibrate" and value is True:
            self._do_baseline(parameter)

        elif name == "selftest" and value is True:
            self._do_selftest(parameter)

    def _read(self, parameter: DeviceParameter) -> Any:
        """Read a parameter value from the device."""
        name = parameter.name

        if name == "data":
            return self._read_data()

        if name == "status":
            self._send_frame("00010800")
            time.sleep(0.2)
            return dict(self._internal_status)

        if name == "scan_progress":
            return self._internal_scan_progress

        if name == "start_scan" or name == "baseline_calibrate" or name == "selftest":
            return False

        # For cached parameters, return last known value
        return parameter.last_known_value

    def _read_data(self) -> pd.DataFrame | None:
        """Read scan data as a DataFrame."""
        if len(self._internal_scan_complete_data) == 0:
            return None
        df = pd.DataFrame(self._internal_scan_complete_data)
        df.columns = ["wavelength", "absorbance"]
        return df

    # ========== Business Operations ==========

    def _send_method_params(self):
        """Send the scan method parameters to the device."""
        start = self._scan_start_wv
        end = self._scan_end_wv
        speed = self._scan_speed
        cmd = (
            f"00010100   17  3  0  0  1   {speed:.1f}   {start:.2f}"
            f"   {end:.2f}  0   1.0  1   500  0   325.00  1  1  1  1"
            f"     0.00  0  0   340.00    120.0"
        )
        self._send_frame(cmd)
        self._wait_ready(timeout=10.0)

    def _do_selftest(self, parameter: DeviceParameter):
        """Execute self-test sequence."""
        self.log("U3900H self-test started")
        self._send_frame("00010002")
        time.sleep(0.5)
        self._send_frame("00010810")
        time.sleep(0.5)
        self._send_frame("00010300")

        if self._wait_ready(timeout=10.0):
            self.log("U3900H self-test phase 1 complete")
        else:
            self.log("U3900H self-test phase 1 timeout", level="warning")

        self._send_method_params()
        self.log("U3900H self-test complete")
        parameter.value = False
        parameter.last_known_value = False

    def _do_baseline(self, parameter: DeviceParameter):
        """Execute baseline calibration."""
        self.log("U3900H baseline calibration started")
        self._internal_baseline_running = True

        if not self._wait_ready(timeout=5.0):
            self.log("U3900H not ready for baseline", level="warning")

        self._send_frame("00010323  1")

        if self._wait_ready(timeout=30.0, poll_interval=0.5):
            self.log("U3900H baseline calibration complete")
        else:
            self.log("U3900H baseline calibration timeout", level="warning")

        self._internal_baseline_running = False
        self._internal_baseline_calibrated = True
        parameter.value = False
        parameter.last_known_value = False

    def _do_scan(self, parameter: DeviceParameter):
        """Execute wavelength scan acquisition."""
        self._internal_scan_data = []
        self._internal_scan_complete_data = []
        self._internal_scan_progress = 0.0
        self._internal_scanning = True

        self.log("U3900H scan started")

        # Send start scan command
        self._send_frame("00010500")
        time.sleep(0.3)

        # Step through wavelengths
        start = self._scan_start_wv
        end = self._scan_end_wv
        step = -1.0 if start > end else 1.0
        total_steps = max(1, int(abs(end - start) / abs(step)) + 1)

        current = start
        for i in range(min(total_steps, 600)):
            if step > 0 and current > end:
                break
            if step < 0 and current < end:
                break

            wv = round(current, 4)
            self._send_frame(f"00010801   {wv:.4f}")
            time.sleep(0.03)
            current += step

        # End scan
        self._send_frame("00010302  0  0")
        time.sleep(0.2)

        self._internal_scanning = False
        self._internal_scan_complete_data = [
            {"w": p["wavelength"], "a": p["absorbance"]}
            for p in self._internal_scan_data
        ]
        self._internal_scan_progress = 100.0

        self.log(f"U3900H scan complete, {len(self._internal_scan_complete_data)} points")

        parameter.value = False
        parameter.last_known_value = False

    # ========== Default Parameters ==========

    _scan_start_wv = 534.0
    _scan_end_wv = 200.0
    _scan_speed = 300.0