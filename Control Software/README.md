# Robochem-Flex

> ***"This mission is too important for me to allow you to jeopardize it."***  
> — *HAL9000 (2001: A Space Odyssey) *

source "/home/jpf/ai4s/Robochem/Robochem_Flex/Control Software/.venv/bin/activate"
cd "/home/jpf/ai4s/Robochem/Robochem_Flex/Control Software"
streamlit run robochem_flex.py

**Robochem-Flex** is the integrated control framework developed by the Noël Research Group (NRG) for automated reaction optimization.  
It unifies **machine learning**, **hardware automation**, and an intuitive **Streamlit-based GUI** into a single modular ecosystem.

---

## Overview

Robochem-Flex coordinates all layers of automated chemistry:
- **Frontend (Streamlit GUI):** interactive control and experiment setup.
- **Hardware Layer (OmniPlatypus):** manages pumps, valves, sensors, and analytics devices.
- **Machine Learning (Robrains):** provides optimization logic using Bayesian and evolutionary algorithms.
- **Spectral Analysis (LAMAS):** provides a layer to do spectral deconvolution and analysis

---

## System Requirements

### Hardware

The software was tested on the following representative configurations:

| System | CPU | RAM   | OS | Notes |
|--------|-----|-------|----|-------|
| Development Workstation | Intel® i7‑1185G7 (4C/8T @ 3.0 GHz) | 32 GB | Windows 11 Education | Primary development and GUI testing |
| Automation Controller | Intel® i5‑13500T (14C/20T @ 1.6–3.0 GHz) | 16 GB | Windows 11 Education | Used to run physical platform with hardware integration |

> The **physical modules** of the Robochem-Flex automation platform are required for real experimental runs.  
> Their design, construction, and configuration are described in the publication’s **Supporting Information**.

---

### Software Dependencies

Robochem-Flex requires **Python 3.12** and the following core packages (tested versions shown):

```
python-dotenv=1.0.1
numpy=1.26.4
pandas=2.2.2
streamlit=1.38
seaborn=0.13.2
openpyxl=3.1.4
pillow=10.0.1
pymoo=0.6.1.1
colorama=0.4.6
pre-commit=3.7.1
pytorch=2.3.0
botorch=0.12.0
gpytorch=1.13
paramiko=3.5.0
fastapi=0.112.2
pyDOE=0.3.8
uvicorn=0.34.2
bronkhorst-propar=1.2.0
nmrglue=0.11
pause=0.3
```

Recommended additional tools:
- **Conda** (environment management)
- **Black** (automatic code formatting)

All dependencies are listed in the environment files:
- `robochem_flex.yml` – strict reproducibility.
- `robochem_flex_alt.yml` – more lenient compatibility.

---

## Installation

### Create and Activate the Conda Environment

```bash
conda env create --file robochem_flex.yml
conda activate robochem_flex
```

If the main environment fails to resolve dependencies, use the alternative file:
```bash
conda env create --file .\robochem_flex_alt.yml
```

---

### Install the Robochem-Flex Components

The platform is modular — install each component as an editable package:

```bash
pip install -e .\backend\Robochem_ML\
pip install -e .\Lamas\
pip install -e .\OmniPlatypus\OmniPlatypus\
```

> Each subpackage includes its own README with further details.

---

## Usage

### Launching the GUI

To start the Robochem-Flex application:

```bash
conda activate robochem_flex
streamlit run .\robochem_flex.py
```

Streamlit will open **two browser tabs**:
- **Interactive GUI** — main control dashboard.
- **ML Log Panel** — live updates from the optimization backend.

Startup may take a few seconds depending on your machine.

---

### Demo Mode

Demo sessions reproducing the campaigns described in the main publication are located in the `Examples/` folder.

To run them:
1. Copy the folder `Examples` into your Robochem data directory (default path: `C:\Users\<username>\Robochem\Examples`).
2. Launch Robochem-Flex and, on the first GUI page, load a session file from one of the subfolders (e.g., `CSx`).  
3. Proceed through all setup pages to reach the **Automation** tab.

> ⚙️ To test the software without real hardware, load the **`CS0_dryrun`** example.  
> This “Human-in-the-Loop” dummy campaign uses simulated results that you can enter manually.

---

## 🧑‍🔬 Authors & Attribution

Developed by the **Noël Research Group (NRG)**  
*University of Amsterdam – Flow Chemistry*

**Contributors:** Simone Pilon, Elia Savino, Oliver Bayley, and the NRG Robochem Team.

---

