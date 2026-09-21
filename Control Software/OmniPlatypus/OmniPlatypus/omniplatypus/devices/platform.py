"""
File: platform.py
Author: Simone Pilon, Elia Savino - Noël Research Group - 2023
GitHub: https://github.com/simone16, github.com/EliaSavino

Description: Interface to conveniently control all devices of an automation platform.
"""

import copy
import os.path
import json
import pandas as pd
from threading import Thread
from typing import Any, Callable

from omniplatypus.utilities.logger import Logger
from omniplatypus.utilities.general import path_to_configuration_folder, run_all
from omniplatypus.devices.errors import DeviceNotImplemented, DeviceError
from omniplatypus.devices.serial_id import KnownDevices
from omniplatypus.procedures.unit_tasks.user_actions import UserActionRequest

from omniplatypus.devices.base.device import BaseDevice
from omniplatypus.devices.base.array import ArrayDevice, ProxyDevice
from omniplatypus.devices.nrg.back_pressure_regulator import (
    BackPressureRegulator,
)
from omniplatypus.devices.nrg.syringe_pump import SyringePump
from omniplatypus.devices.nrg.sampler import Sampler
from omniplatypus.devices.bronkhorst.mass_flow_controller import (
    MassFlowController,
)
from omniplatypus.devices.nrg.solar_simulator_light import SolarLightSource
from omniplatypus.devices.omron.temperature import TemperatureControl
from omniplatypus.devices.nrg.phase_sensor import PhaseSensorArray
from omniplatypus.devices.nrg.gpio import GpioArray
from omniplatypus.devices.nrg.light import LightArray
from omniplatypus.devices.ika.heating_plate import HeatingPlate
from omniplatypus.devices.nrg.rama_berry import RamaBerry
from omniplatypus.devices.magritek.spinsolve import SpinsolveClient
from omniplatypus.devices.nrg.chromtroller import HPLCClient
from omniplatypus.devices.nrg.u3900h_spectrometer import U3900HSpectrometer


class SampleHolder:
    """
    Holds information over a sample holder.
    The information on the different holder types is found in a configuration file.
    """

    def __init__(self):
        self.min_volume = None
        self.max_volume = None
        self.min_depth = None
        self.max_depth = None
        self.components = {}


class Platform:
    """
    Interface to control a set of physical devices within an automation platform.

    Usage:
        The components of a platform must be specified within a json configuration file.
        The file contains all information necessary to build the platform interface.

        To access the devices, use:
            ```
            platform = Platform()
            platform.build('my_platform')

            platform['pump']['pump_volume'] = 100
            or
            platform.devices['pump']['pump_volume'] = 100
            ```

    Syntax of platform configuration file:
        The file must contain a dictionary of 'platform_name' -> platform_data pairs.
        platform_data is in turn a dictionary of 'device_name' -> device_data pairs.
        device_data contains 'name' -> value pairs. The following pairs should always be specified:

            'tags' -> list of strings specifying user-defined tags.
            'class' -> str identifying a class within DEVICE_CONSTRUCTORS to be used as the device interface.
            'serial' -> dict[str, str] specifying a 'known_device'
            or
            'IP' -> dict[str, int | str] specifying IP address and port for socket interface.
            'setup' -> Custom options defined per-device (see device documentation).

    Attributes:
        @var devices: dict[str, BaseDevice]
            Devices available within the built platform.
        @var sample_holders: dict
            Information on the sample holders used by the platform samplers.
        @var samples: pd.DataFrame | None
            Information on the samples and vials in the platform samplers.
        @var user_action_requester: Callable[[UserActionRequest], bool] | None
            A function to call to request the user to provide a vial o perform some non-automated task.
            The function should take a message for the user as a UserActionRequest (or subclass) argument and return
            True if the task should be run again (continue experiment), or False to exit (stop experiment).
            The experiment should set this before building the platform, but it is optional.
    """

    device_constructors = {
        "back_pressure_regulator": BackPressureRegulator,
        "syringe_pump_nrg": SyringePump,
        "liquid_handler_sampler": Sampler,
        "mass_flow_controller": MassFlowController,
        "solar_light_source": SolarLightSource,
        "e5_c_pid_control": TemperatureControl,
        "phase_sensor_array": PhaseSensorArray,
        "gpio_array": GpioArray,
        "light_array": LightArray,
        "heating_plate_ika": HeatingPlate,
        "rama_berry": RamaBerry,
        "spinsolve_client": SpinsolveClient,
        "hplcclient": HPLCClient,
        "u3900h_spectrometer": U3900HSpectrometer,
    }
    default_config_filename = "platform_config.json"
    default_storage_filename = "platform_storage.json"
    default_holder_types_filename = "sample_holder_types.json"

    devices: dict[str, BaseDevice | ProxyDevice]
    sample_holders: dict
    samples: pd.DataFrame | None
    user_action_requester: Callable[[UserActionRequest], bool] | None

    def __init__(self):
        self.devices = {}
        self.sample_holders = {}
        self.samples = None
        self.user_action_requester = None
        self._known_devices = KnownDevices()
        self._platform_name = "Platform"
        self._ready = False
        self._storage_root = None
        self._platform_constants = {}

    def __del__(self):
        self.clear()

    @property
    def storage_root(self) -> str | None:
        """
        Root folder for storing files.

        @return: str
            Path to root storage folder.
        """
        return self._storage_root

    @property
    def constants(self) -> dict:
        """
        Platform-specific constant values as provided by the platform_config.json file.
        These are characteristics of the platform as a whole, not of any specific device.
        Some experiments require specific values to be set.

        @return: dict
            A dictionary of values copied from the platform_config.json 'constants' section.
        """
        return copy.deepcopy(self._platform_constants)

    @classmethod
    def default_config_path(cls) -> str:
        """
        The default path to the platform configuration file.

        @return: str
            The path to the default configuration file.
        """
        return os.path.join(path_to_configuration_folder(), cls.default_config_filename)

    @classmethod
    def default_storage_path(cls) -> str:
        """
        The default path to the platform persistent storage file.

        @return: str
            The path to the default persistent storage file.
        """
        return os.path.join(
            path_to_configuration_folder(), cls.default_storage_filename
        )

    @classmethod
    def default_holder_types_path(cls) -> str:
        """
        The default path to the vial holder configuration file.

        @return: str
            The path to the default configuration file.
        """
        return os.path.join(
            path_to_configuration_folder(), cls.default_holder_types_filename
        )

    def parse_holder_types(self, config: dict) -> None:
        """
        Fills self.vial_holders with the data coming from a configuration file.

        @param config: dict
            The configuration described within the file.
        """
        for name, data in config.items():
            holder = SampleHolder()
            try:
                holder.max_volume = data["max_volume"]
                holder.min_volume = data["min_volume"]
                holder.min_depth = data["min_depth"]
                holder.max_depth = data["max_depth"]
                holder.components = data["components"].copy()
            except KeyError as e:
                e.add_note("Occurred while parsing holder types.")
                e.add_note(f"Each holder must define '{e.args[0]}'.")
                raise
            self.sample_holders[name] = holder

    @classmethod
    def generate_device_docs(cls, path: str):
        """
        Generate documentation for all devices and store it in the folder specified.

        @param path: str
            Path to folder for docs.
        """
        for name, device_class in cls.device_constructors.items():
            device = device_class()
            filename = os.path.join(path, device.__class__.__name__ + ".md")
            with open(filename, "w") as file:
                file.write(device.usage())
                file.write(f"\nPlatform class identifier: '{name}'.")

    def generate_platform_docs(self, path: str):
        """
        Generate documentation for the devices within the built platform.
        Does not include all devices, but the docs will reflect the capability of the
        actual platform.

        @param path: str
            Path to folder for docs.
        """
        path = os.path.join(path, self._platform_name)
        if not os.path.isdir(path):
            os.makedirs(path)
        for name, device in self.devices.items():
            filename = os.path.join(path, device.__class__.__name__ + ".md")
            with open(filename, "w") as file:
                file.write(device.usage())

    def get_platform_config(self, name: str, config: str | dict | None = None) -> dict:
        """
        Get the configuration options for a given platform.

        @param name: str
            The name of the platform as it appears in the config data / file.
        @param config:
            Configuration data or path to configuration file.
            If unspecified the default path is used (project-root/config/platform_config.json).
            If a dictionary is used, this is assumed to have the same structure as the configuration file.
        @return: dict
            Configuration data for the requested platform.
            The structure is that of the configuration file, except only data for the platform devices with
            the specified name is returned.
        """
        if config is None:
            config = Platform.default_config_path()
        if isinstance(config, str):
            with open(config, "r") as platform_config_file:
                try:
                    platforms = json.load(platform_config_file)
                except json.JSONDecodeError as e:
                    e.add_note(f"Originated from Platform builder (target: '{name}').")
                    self.log(e)
                    raise
        elif isinstance(config, dict):
            platforms = config
        else:
            error = TypeError(
                f"Invalid type for argument config_file: '{type(config)}'."
            )
            error.add_note(f"Originated from Platform builder (target: '{name}').")
            self.log(error)
            raise error
        if name not in platforms.keys():
            error = KeyError(f"Unknown platform: '{name}'.")
            error.add_note(f"Originated from Platform builder (target: '{name}').")
            self.log(error)
            raise error
        return platforms[name]

    def storage_get(self, name: str, device: str | None = None) -> Any:
        """
        Retrieve a variable from the platform persistent storage.
        Stored variables are preserved between runs.

        @param name: str
            The identifier used for the variable.
        @param device: str | None = None
            An optional device identifier for variables within a device namespace.
        @return: Any
            The value retrieved from the persistent storage file.
            Returns None if the value is not found.
        """
        with open(self.default_storage_path()) as storage_file:
            try:
                storage = json.load(storage_file)
            except json.JSONDecodeError as e:
                e.add_note(f"Originated from Platform '{name}'.")
                self.log(e)
                raise
        try:
            storage = storage[self._platform_name]
            if device is not None:
                storage = storage["devices"][device]
            else:
                storage = storage["global"]
            return storage[name]
        except KeyError:
            return None

    def storage_put(self, name: str, value: Any, device: str | None = None) -> None:
        """
        Retrieve a variable from the platform persistent storage.
        Stored variables are preserved between runs.

        @param name: str
            The identifier used for the variable.
        @param value: Any
            The value to store.
        @param device: str | None = None
            An optional device identifier for variables within a device namespace.
        """
        try:
            with open(self.default_storage_path()) as storage_file:
                try:
                    storage = json.load(storage_file)
                except json.JSONDecodeError as e:
                    e.add_note(f"Originated from Platform '{name}'.")
                    self.log(e)
                    raise
        except FileNotFoundError:
            storage = {self._platform_name: {"devices": {}, "global": {}}}
        if device is not None:
            storage["devices"][device][name] = value
        else:
            storage["global"][name] = value
        with open(self.default_storage_path(), "w") as storage_file:
            json.dump(storage, storage_file, indent=4)

    def build(
        self,
        platform_name: str,
        config_file: str | dict | None = None,
        devices: set | list | None = None,
        update_docs: bool = True,
        storage_path: str | None = None,
        open_gui: bool = True,
        allow_slack_messages: bool = False,
    ) -> None:
        """
        Builds the interface for the specified platform.

        @param platform_name: str
            The name of the platform as specified in the configuration file.
        @param config_file: str | dict | None = None
            Optional path to a configuration file or configuration data.
            If unspecified the default path is used (project-root/config/platform_config.json).
            If a dictionary is used, this is assumed to have the same structure as the configuration file.
        @param devices: set | list | None
            If specified, only the listed device names will be built.
        @param update_docs: bool = True
            If True, writes the documentation for the platform being built (by default, uses the doc folder).
        @param storage_path: str | None = None
            Path to storage location for files generated by the platform, such as logs.
        @param open_gui: bool = True
            The device module GUI will be started. This allows real-time monitoring of platform operations.
            Note: At the moment, logging is only provided via the GUI and logfiles.
        @param allow_slack_messages: bool = False
            Set to True to allow the platform to send messages through Slack in case of errors.
            Note: slack token must be set up properly for this to work.
        """
        if self._ready:
            self.clear()  # Erase previous platform, if built
        self._platform_name = platform_name
        self._storage_root = storage_path

        Logger.start_logging_thread(
            platform=platform_name,
            use_slack=allow_slack_messages,
            logs_path=self._storage_root,
            use_gui=open_gui,
        )
        self.log(f"Building platform...", indent="enter")

        platform_config = self.get_platform_config(
            name=platform_name, config=config_file
        )
        try:
            platform_devices = platform_config["devices"]
        except KeyError as error:
            error.add_note(
                "platform_config.json file must specify 'devices' for "
                f"each platform (not found for {self._platform_name})!"
            )
            self.log(error)
            raise
        self._platform_constants = platform_config.get("constants", dict())
        holder_types_config_path = Platform.default_holder_types_path()
        with open(holder_types_config_path, "r") as holder_config_file:
            try:
                holders = json.load(holder_config_file)
                self.parse_holder_types(holders)
            except json.JSONDecodeError as e:
                e.add_note(
                    f"Originated from Platform builder (target: '{platform_name}')."
                )
                self.log(e)
                raise

        devices_to_build = []
        if devices is not None:
            devices = set(devices)
            for device_name in devices:
                if device_name in platform_devices.keys():
                    devices_to_build.append(device_name)
                else:
                    message = f"Device '{device_name}' not found in configuration file for '{platform_name}'."
                    error = ValueError(message)
                    self.log(error)
                    raise error
        else:
            devices_to_build = list(platform_devices.keys())

        build_threads = []
        for device_name in devices_to_build:
            device_data = platform_devices[device_name]
            build_device_thread = Thread(
                target=self.build_device,
                name=f"builder for {device_name}",
                kwargs={
                    "device_name": device_name,
                    "device_data": device_data,
                },
            )
            build_threads.append(build_device_thread)
        run_all(*build_threads)

        if update_docs:
            self.generate_platform_docs(os.path.join("", "doc", "platforms"))

        self._ready = True
        self.log("Built platform.", indent="exit", level="ok")

    def _connect_serial_device(
        self,
        device_data: dict,
        device_controller: BaseDevice,
    ):
        """
        Attempts to connect to a device based on the provided device data.

        @param device_data: dict
            Dictionary containing data about the device connection as found in the configuration file.
            Must name a 'known_device'.
        @param device_controller: BaseDevice
            Device object

        @raise: DeviceError
            If there's an issue with the 'known_device' attribute or if the specified device is not found.
        """
        # Check if 'known_device' attribute is present in device_data
        if "known_device" not in device_data.keys():
            error = DeviceError(
                "No 'known_device' attribute specified within 'serial': cannot connect.",
                device=device_controller,
            )
            self.log(error, indent="continue")
            raise error

        # Retrieve the 'known_device' name
        known_device_name = device_data["known_device"]

        # Check if the known device name is recognized
        if known_device_name not in self._known_devices.keys():
            error = DeviceError(
                device_controller,
                "'known_device' attribute is not known: cannot connect.",
            )
            self.log(error, indent="continue")
            raise error

        # Attempt to connect to the device using its comport
        comport = self._known_devices[known_device_name]
        if comport is not None:
            device_controller.open(comport=comport)
        else:
            error = DeviceError(
                "Serial device not found: cannot connect.", device=device_controller
            )
            self.log(error, indent="continue")
            raise error

    def _connect_IP_device(
        self,
        device_data: dict,
        device_controller: BaseDevice,
    ):
        """
        Attempts to connect to an IP device based on the provided device data.

        @param device_data: dict
            Dictionary containing data about the device connection as found in the configuration file.
            Must name a 'host' and a 'port'.
        @param device_controller: BaseDevice
            Device object

        @raise: DeviceError:
            If there's an issue with the 'known_device' attribute or if the specified device is not found.
        """

        if "host" not in device_data.keys() or "port" not in device_data.keys():
            error = DeviceError(
                "Has tag 'IP' but no 'host/port' attribute: cannot connect",
                device=device_controller,
            )
            self.log(error, indent="continue")
            raise error

        host, port = device_data["host"], device_data["port"]
        if host is not None and port is not None:
            device_controller.open(host=host, port=port)
        else:
            error = DeviceError(
                "IP device not found: cannot connect.",
                device=device_controller,
            )
            self.log(error, indent="continue")
            raise error

    def build_device(
        self,
        device_name: str,
        device_data: dict,
    ) -> None:
        """
        Build a single device within this platform.

        This is done in 4 steps:
        1. A controller class is created for the device.
        2. A connection is established with the device.
        3. The device setup options are ran.
        4. The device is initialized.

        @param device_name: str
            The name which will identify the device within the platform.
        @param device_data: dict
            The device data from platform_config.
        """
        # Create device object
        self.log(f"Building device '{device_name}'...")
        if "class" not in device_data.keys():
            error = DeviceNotImplemented(
                f"Device '{device_name}' does not specify a class."
            )
            error.add_note(
                f"Originated from Platform builder (target: '{self._platform_name}', device: '{device_name}')."
            )
            self.log(error, indent="continue")
            raise error
        constructor_name = device_data["class"].lower()
        if constructor_name not in Platform.device_constructors:
            error = DeviceNotImplemented(
                f"No class found corresponding to '{constructor_name}'."
            )
            error.add_note(
                f"Originated from Platform builder (target: '{self._platform_name}', device: '{device_name}')."
            )
            self.log(error, indent="continue")
            raise error
        device_controller: BaseDevice = Platform.device_constructors[constructor_name]()
        if "tags" not in device_data.keys():
            self.log(
                f"No tags defined for '{device_name}'.",
                level="warning",
            )
        device_controller.tags = copy.deepcopy(device_data["tags"])
        device_controller.specific_name = device_name
        self.devices[device_name] = device_controller
        device_controller.log("Created device.", level="ok")

        # Connect to device
        device_controller.log("Connecting...", indent="enter")
        if "serial" in device_data.keys():
            self._connect_serial_device(device_data["serial"], device_controller)
        elif "IP" in device_data.keys():
            self._connect_IP_device(device_data["IP"], device_controller)
        else:
            error = DeviceError(
                "No connection method specified: cannot connect.",
                device=device_controller,
            )
            device_controller.log_exception(error)
            raise error
        if not device_controller.is_open():
            error = DeviceError("Device was not connected.", device=device_controller)
            device_controller.log_exception(error)
            raise error
        device_controller.log("Connected.", indent="exit", level="ok")

        # Setup device using setup options
        device_controller.log("Running setup options...", indent="enter")
        if "setup" in device_data.keys():
            device_controller.setup(**device_data["setup"])
        else:
            device_controller.setup()
        if isinstance(device_controller, ArrayDevice):
            subdevices = device_controller.proxies()
            for name in subdevices:
                if name in self.devices.keys():
                    self.log(
                        f"Subdevice id '{name}' conflicts with the id\
                         of existing device '{self.devices[name].complete_name}'.",
                        level="warning",
                    )
                    continue
                subdevice = device_controller.proxy(name)
                subdevice.specific_name = name
                self.devices[name] = subdevice
        device_controller.log("Setup completed.", level="ok", indent="exit")

        # Initialize devices
        device_controller.log("Initializing...", indent="enter")
        device_controller.initialize()
        device_controller.log(
            "Initialization completed.",
            level="ok",
            indent="exit",
        )

        # Close device if needs to be re-opened
        if not device_controller.keep_open:
            device_controller.close()

        self.log(f"Built device '{device_name}'...", level="ok")

    def __getitem__(self, device_name: str) -> BaseDevice:
        """
        Gives access to the individual devices within the platform.

        @param device_name: str
            The name used to identify the device in the configuration file.
        @return: BaseDevice
            The device object associated with the given name.
        @raise KeyError:
            Raises an exception if the device is not found.
        """
        return self.devices[device_name]

    def device_id(self, device: BaseDevice | ProxyDevice) -> str | None:
        """
        Get the identifier corresponding to the device.
        The identifier is such that self[device_id] returns the device.

        @param device: BaseDevice | ProxyDevice
            A device within this platform.
        @return: str | None
            The identifier used by the platform for the device, or None if the device is not found within the platform.
        """
        for device_id, platform_device in self.devices.items():
            if device is platform_device:
                return device_id
        return None

    def log(self, message: str | Exception, **kwargs):
        """
        Log message in Platform log.
        For available kwargs, see Logger.log_message in devices/Logger.py
        """
        kwargs["priority"] = 2  # corresponds to high verbosity
        Logger.log_message(message=message, origin=self._platform_name, **kwargs)

    def keys(self):
        """
        Returns the names of all devices.

        @return: dict_keys
            Configurations names.
        """
        return self.devices.keys()

    def clear(self) -> None:
        """Remove all devices from platform and close connections."""
        Logger.log_message(
            "Clearing platform...",
            origin=self._platform_name,
        )

        try:
            close_threads = []
            for name, device in self.devices.items():
                if not isinstance(device, ProxyDevice) and device.is_open():
                    close_device_thread = Thread(
                        target=device.close, name=f"close {device}"
                    )
                    close_threads.append(close_device_thread)
            run_all(*close_threads)
        finally:
            self.devices = {}
            Logger.log_message(
                "Platform cleared.",
                level="ok",
                origin=self._platform_name,
            )
            Logger.stop_logging_thread()
            self._ready = False

    def __str__(self) -> str:
        """Name of the platform."""
        return self._platform_name
