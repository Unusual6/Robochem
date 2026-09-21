"""
File: temperature.py
Author: Simone Pilon - Noël Research Group - 2023
Github: https://github.com/simone16

Description: Interface for controlling Modbus-based PID temperature control model Omron E5_C.
"""

import enum
from enum import Flag
import pymodbus.exceptions
from omniplatypus.devices.base.device_modbus import (
    ModbusDevice,
    ModbusParameter,
    RegisterType,
)
from omniplatypus.devices.base.device import ParameterAccess


class E5CStatus(Flag):
    """Omron E5_C Status Registers flags."""

    HEATER_OVERCURRENT_CT1 = 0x00000001
    HEATER_CURRENT_HOLD_CT1 = 0x00000002
    AD_CONVERTER_ERROR = 0x00000004
    HS_ALARM = 0x00000008
    RSP_INPUT_ERROR = 0x00000010
    INPUT_ERROR = 0x00000040
    POTENTIOMETER_INPUT_ERROR = 0x00000080
    CONTROL_OUTPUT_OPEN = 0x00000100
    CONTROL_OUTPUT_CLOSE = 0x00000200
    HB_ALARM_CT1 = 0x00000400
    HB_ALARM_CT2 = 0x00000800
    AL1 = 0x00001000
    AL2 = 0x00002000
    AL3 = 0x00004000
    PROGRAM_END_OUTPUT = 0x00008000
    EV1 = 0x00010000
    EV2 = 0x00020000
    EV3 = 0x00040000
    EV4 = 0x00080000
    WRITE_MODE = 0x00100000
    NON_VOLATILE_MEM = 0x00200000
    SETUP_AREA = 0x00400000
    AT_EXEC_CANCEL = 0x00800000
    STOP = 0x01000000
    COMM_WRITE = 0x02000000
    AUTO_MAN = 0x04000000
    PROGRAM_START = 0x08000000
    HEATER_OVERCURRENT_CT2 = 0x010000000
    HEATER_CURRENT_HOLD_CT2 = 0x020000000
    HS_ALARM_CT2 = 0x080000000

    WB1 = 0x100000000
    WB2 = 0x200000000
    WB3 = 0x400000000
    WB4 = 0x800000000
    WB5 = 0x1000000000
    WB6 = 0x2000000000
    WB7 = 0x4000000000
    WB8 = 0x8000000000

    EV5 = 0x10000000000
    EV6 = 0x20000000000

    INVERT = 0x100000000000
    SP_RAMP = 0x200000000000

    SP_MODE = 0x0800000000000
    AL4 = 0x10000000000000

    SUB1 = 0x1000000000000000


class TemperatureControl(ModbusDevice):
    """
    Handles communication with PID temperature control units type Omron E5_C via Serial Modbus
    communication protocol.
    """

    def __init__(self):
        ModbusDevice.__init__(self)

        self.generic_name = "E5_C temperature control"

        parameter = ModbusParameter(
            name="enable",
            access_level=ParameterAccess.W,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.COMMAND,
            internal_id=0x01,
        )
        parameter.description = "Enable heating (run/stop)"
        parameter.values = {"ON": 0x00, "OFF": 0x01}
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="temperature",
            access_level=ParameterAccess.R,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2000,
        )
        parameter.description = "Temperature measured"
        parameter.units = "°C"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="temperature_sp",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2103,
        )
        parameter.description = "Temperature setpoint"
        parameter.units = "°C"
        parameter.min_value = 0.0
        parameter.max_value = 500.0
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="status",
            access_level=ParameterAccess.R,
            value_type=E5CStatus,
            internal_type=Flag,
            register_type=RegisterType.HOLDING,
            internal_id=0x2406,
        )
        parameter.description = "Status flags"
        parameter.data_length = 4
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="int_sp",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2002,
        )
        parameter.description = "Internal temperature setpoint"
        parameter.units = "°C"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="heat_current",
            access_level=ParameterAccess.R,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2003,
        )
        parameter.description = "Heater 1 current value monitor"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="heating",
            access_level=ParameterAccess.R,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2004,
        )
        parameter.description = "manipulated variable monitor (heating)"
        parameter.units = "%"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="pid_p",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2A00,
        )
        parameter.description = "PID proportional band (heating)"
        parameter.units = " EU"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="pid_i",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2A01,
        )
        parameter.description = "PID integral time (heating)"
        parameter.units = " S"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="pid_d",
            access_level=ParameterAccess.RW,
            value_type=float,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2A02,
        )
        parameter.description = "PID derivative time (heating)"
        parameter.units = " S"
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="pid_or_onoff",
            access_level=ParameterAccess.RW,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2D14,
        )
        parameter.description = "PID or on/off (heating)"
        parameter.values = {"ON_OFF": 0x00, "PID_CONTROL": 0x01}
        self.add_parameter(parameter)

        # todo when selecting an input with 1/10 T, adjust all values read/written.
        parameter = ModbusParameter(
            name="input_type",
            access_level=ParameterAccess.RW,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.HOLDING,
            internal_id=0x2C00,
        )
        parameter.description = "Input type selection"
        parameter.values = {
            "Pt_0": 0x00,
            "Pt_1n": 0x01,
            "Pt_1p": 0x02,
            "JPt_0": 0x03,
            "JPt_1": 0x04,
            "K_0": 0x05,
            "K_1": 0x06,
            "J_0": 0x07,
            "J_1": 0x08,
            "T_0": 0x09,
            "T_1": 0x0A,
            "E": 0x0B,
            "L": 0x0C,
            "U_0": 0x0D,
            "U_1": 0x0E,
            "N": 0x0F,
            "R": 0x10,
            "S": 0x11,
            "B": 0x12,
            "W": 0x13,
            "PLII": 0x14,
            "IR1": 0x15,
            "IR2": 0x16,
            "IR3": 0x17,
            "IR4": 0x18,
            "EXT1": 0x19,
            "EXT2": 0x1A,
            "EXT3": 0x1B,
            "EXT4": 0x1C,
            "EXT5": 0x1D,
            "EXT6": 0x1E,
        }
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="comm_write",
            access_level=ParameterAccess.W,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.COMMAND,
            internal_id=0x00,
        )
        parameter.description = "Communications writing"
        parameter.values = {"OFF": 0x00, "ON": 0x01}
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="autotune",
            access_level=ParameterAccess.W,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.COMMAND,
            internal_id=0x03,
        )
        parameter.description = "Autotune command"
        parameter.values = {
            "AT_CANCEL": 0x00,
            "AT_EXEC_100PCT": 0x01,
            "AT_EXEC_40PCT": 0x02,
        }
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="write_mode",
            access_level=ParameterAccess.W,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.COMMAND,
            internal_id=0x04,
        )
        parameter.description = "Write mode"
        parameter.values = {"BACKUP": 0x00, "RAM_WM": 0x01}
        self.add_parameter(parameter)

        parameter = ModbusParameter(
            name="save_ram_data",
            access_level=ParameterAccess.W,
            value_type=int,
            internal_type=int,
            register_type=RegisterType.COMMAND_ACTION,
            internal_id=0x05,
        )
        parameter.description = "Save RAM data to EEPROM"
        parameter.values = {"EXECUTE": 0x00}
        self.add_parameter(parameter)

    def open(self, comport: str):
        """
        Connects to the device. The connection must open before data can be sent or received.

        @param comport: str
            Identifier of the serial port to which the device is connected.
        """
        try:
            ModbusDevice.open(self, comport)
            self.__setitem__("comm_write", "ON")
            self.__setitem__("write_mode", "RAM_WM")
            self.__setitem__("input_type", "K_1")
            # If another input type is used, make sure to check the decimal point position.
            # print(self._modbus_client.read_register('decimal point monitor')[1])
            self.__setitem__("pid_or_onoff", "PID_CONTROL")
        except pymodbus.exceptions.ModbusIOException as e:
            self.log(str(e), decorate=False)
            self.log(f"Failed to connect on '{comport}'.", level="error")
            self._client.disconnect()
