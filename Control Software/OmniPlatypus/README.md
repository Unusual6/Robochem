# <img src="imgs/Omniplatypus.jpg" alt="Omniplatypus Logo" height="100" style="vertical-align: middle;">OmniPlatypus

> ***"We're stuck with technology when what we really want is just stuff that works"***  
> — *Douglas Adams (The Salmon of Doubt) *


PC (Windows)
 ├── USB ──→ Arduino 串口设备 (泵、采样器、光源、传感器、GPIO)  [9600 baud]
 ├── RS-485 ─→ Modbus 温控器 (Omron)
 ├── 以太网 ─→ HPLC / NMR / 拉曼 (TCP Socket)
 ├── SSH ──→ 树莓派 (UV/拉曼光谱)
 └── USB ──→ Bronkhorst 流量控制器




The **NRG's next-generation platform for Automated Chemistry**, providing a flexible, modular, and easily extendable framework to control, coordinate, and analyze complex experimental setups.

OmniPlatypus is designed for **atomic customizability**: every device, unit task, and experimental procedure can be configured, reused, or replaced independently. The platform supports seamless communication between analytical instruments, pumps, sensors, and other devices — enabling full workflow automation.

---

## Building the Package

If you’re unsure whether the local package is up to date, rebuild it manually.

From the directory containing the `setup.py` file, run:
```bash
python setup.py sdist bdist_wheel
```

Then uninstall and reinstall the package:
```bash
pip uninstall omniplatypus -y
pip install dist/omniplatypus-<version>.whl
```

---

## Installation

Install **OmniPlatypus** as an *editable package* (recommended for development and frequent updates).

### From the Command Line

1. Activate your environment (`conda activate omniplatypus_env`)
2. Locate the root path of the OmniPlatypus repository
3. Run:
   ```bash
   pip install -e <path-to-repo>/omniplatypus
   ```
4. The `-e` flag ensures your installation automatically reflects local changes.
5. Enjoy automating your chemistry.

---

### Within PyCharm

1. Open the **Python Packages** panel.
2. Click **Add Package → From Disk**.
3. Select the path:  
   `<path-to-repo>/OmniPlatypus`
4. Make sure **“Install as editable (-e)”** is checked.
5. Have fun experimenting.

---

## Project Structure

OmniPlatypus follows a clear, modular structure:

```
omniplatypus/
│
├── procedures/
│   ├── experiments/       # Full experimental workflows (e.g., photochemistry, thermochemistry)
│   ├── unit_tasks/        # Atomic operations: driving, sampling, measuring, sensing, reactor
│   └── analytics/         # Interfaces for analytical instruments (to be extended)
│
├── devices/               # Hardware-specific communication drivers (if present)
│
├── utils/                 # Shared utilities, configuration, and logging (optional)
│
└── __init__.py
```

### Core Concepts

More specific docs about all the below can be found in the dostring of each class.

#### Unit Tasks
Atomic building blocks that define low-level operations, implemented as **class factories** under:
```
procedures/unit_tasks/base_unit_task.py
```

Unit tasks include:
- **Driving** – pump and flow control (`driving_pumps.py`, `hplc_driving.py`)
- **Measuring** – analytical interfacing (`raman_spec.py`)
- **Sampling** – liquid handling and injection operations
- **Sensing** – optical/physical sensor integration (`phase_sensors.py`)
- **Reactor** – light and temperature control (`reactor/light.py`)

These tasks can be recombined to build complex experiments.

#### Experiments
Full workflow definitions found in:
```
procedures/experiments/
```
Examples include:
- `photochemistry.py` — photo-driven reaction sequences  
- `thermochemistry.py` — temperature-controlled processes  
- `chemistry.py` — general reaction orchestration  

Each experiment defines the logical combination of unit tasks into a cohesive experimental sequence.

#### Analytics
Modules (e.g. Raman spectroscopy, UV-Vis) define how analytical instruments communicate with the platform for data acquisition and interpretation.

---

## Philosophy

OmniPlatypus is built to support **"atomic automation"** — each element of an experiment (pump, sensor, analysis tool) is a self-contained, replaceable module.  
This allows:
- Rapid prototyping of new experimental workflows  
- Seamless scaling from single devices to fully automated laboratories  
- Consistent communication standards across heterogeneous instruments  

---

## Registering a serial device

Devices within the platform are automatically recognized from a list of known devices. Those connected via USB are recognized by comparing their hardware-id and a combination of other 
identifiers. Note that some USB devices do not have an hardware ID. If many such devices are present, it can be impossible for the module to correctly recognize different devices.
To add a device to the list, take the following steps:

1. Plug the USB device in, making sure you can easily identify it from a list (disconnect any other unknown device which might confuse you).
2. Launch the "add_serial_device.py" script from the project root via the command line:
	```bash
	conda activate robochem_flex
	cd <project root>\OmniPlatypus
	python OmniPlatypus\omniplatypus\scripts\add_serial_device.py
	```
3. Identify your device from the list and follow the instructions, the script will store as much information as possible about the device in order to recognize it later.
4. If the device is self-developed, you can add a custom identifier to it and register its value too. This can help in case of identical Arduino boards, but slows down the recognition process, as the serial connection must be opened to read the identifier, which requires a few seconds.

> [!note]
> All scripts within "OmniPlatypus\omniplatypus\scripts" must be run from the package root folder ("\<project root\>\OmniPlatypus").

## Defining an automation platform

Platforms configuration is defined within the "platform_config.json" file, which can be found in the "\<project root\>\OmniPlatypus\OmniPlatypus\omniplatypus\config\" folder.
Here, a list of devices is given for each platform which can be controlled. The desired platform is selected when setting up an experiment within the GUI.
See the provided platform_config file for a complete example, the overall file structure is given below.

```json
  "Platform 1": {
    "constants": {
      ...
    },
    "devices": {
      ...
    },
    "Gui_Specs": {
      ...
    }
  }.
  "Platform 2": {
    "constants": {
      ...
    },
    "devices": {
      ...
    },
    "Gui_Specs": {
      ...
    }
  },
  ...
```

Each platform defines constant values, which are retrieved at runtime but should not be easily changed by the user. They are grouped hierarchically depending on which stage of the
process they apply to and which combination of equipment.
Under 'devices', each module of the platform is listed under a name which will be used to identify it in the experiment. An example is given below.

```json
    "devices": {
      "Main_Pump_1": {
        "tags": [
          "liquid",
          "flow",
          "3w_valve"
        ],
        "class": "syringe_pump_nrg",
        "serial": {
          "known_device": "main_pump_op1"
        },
        "setup": {
          "syringe_volume": "10.0mL",
          "syringe_stepperml": "7755.0",
          "max_flowrate": 60.0,
          "valve": true,
          "reservoir_valve_position": "OFF",
          "aux-valve": true
        }
      },
      ...
   },

```

Under 'tags' the user can specify a number of keywords. These can be retrieved within the user code, but are otherwise ignored by the omniplatypus module.
Under 'class' a name specifying the correct interface class for this device must be given. Valid entries are listed in omniplatypus.devices.Platform.DEVICE_CONSTRUCTORS.
Under 'serial', the name given to the USB device must be provided, as defined when calling the 'add_serial_device' script. Alternatively, the keyword 'IP' is used as follows:
```json
        "IP": {
          "host": "192.168.1.202",
          "port": 99999
        }
```
if the device is meant to connect via a socket IP interface. Host and port must match the address that the device can be reached at from the controlling computer.
Under 'setup' a number of device parameters are set, such as the diameter of the syringe in a pump or the location of the vial holders within a sampler unit.
Information on the available setup options for each device is given in the "\<project root\>\OmniPlatypus\doc" folder.

## Testing

To run the test suite (if included):
```bash
python -m unittest OmniPlatypusTests
```

---

## Contributors

Developed within the **Noël Research Group** (NRG)  
*University of Amsterdam* — Department of Flow Chemistry

Main Contributors:
Simone Pilon
Elia Savino
Oliver Bayley

---

