<img src="Control Software/utils/NRG_logo.png" alt="NRG Logo" height="100">

# Robochem-Flex

This repository bundles the **software, device files, and example data** for the  
**Robochem-Flex** platform: a modular self-driving laboratory framework.  

---

## 🔎 Repository Structure

- **Control Software**  
  Streamlit application and supporting backend code for configuring and running optimisation campaigns.

- **Devices**  
  Hardware resources such as CAD models, firmware, and PCB designs for the actuators and sensors used on the platform.

- **Examples**  
  Sample configuration files demonstrating how to set up a campaign and define stock solutions or vial layouts.

Each directory contains more detailed documentation specific to its contents.  
To run the platform optimization code, please refer to the README.md file within the Control Software folder.

---

## 🧑‍🔬 Authorship & Credits

The contents of this repository have been developed by:  

- **Dr. Simone Pilon** – University of Amsterdam, Noël Research Group
- **Ir. Elia Savino** – University of Amsterdam, Noël Research Group 
- **Dr. Oliver M. Bayley** – University of Amsterdam, Noël Research Group

for full credits on the project, please see the [accompanying publication](https://chemrxiv.org/doi/10.26434/chemrxiv-2025-73xqf).

If you use any part of this repository, please cite the accompanying publication.

---

## ⚖️ Licensing

The contents of this repository are licensed under the Apache License, Version 2.0.
For more information, consult the NOTICE and LICENSE files.

Copyright 2025 [Noël Research Group](https://www.noelresearchgroup.com).
运行命令
streamlit run robochem_flex.py