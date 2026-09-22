# U-3900H UV-Vis Spectrometer usage


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
    
## Parameters:

| Name | Access | Type | Description | Values |
|------|--------|------|-------------|--------|
| **start_wavelength** | READ/WRITE | float | Scan start wavelength| 190.0 <= value <= 1100.0 nm, | 
| **end_wavelength** | READ/WRITE | float | Scan end wavelength| 190.0 <= value <= 1100.0 nm, | 
| **scan_speed** | READ/WRITE | float | Scan speed| 1.0 <= value <= 3000.0 nm/min, | 
| **data** | READ ONLY | DataFrame | Spectral scan data (wavelength, absorbance)| | 
| **start_scan** | READ/WRITE | bool | Start scan acquisition. Set to True to trigger.| | 
| **baseline_calibrate** | READ/WRITE | bool | Trigger baseline calibration. Set to True to trigger.| | 
| **selftest** | READ/WRITE | bool | Trigger device self-test. Set to True to trigger.| | 
| **status** | READ ONLY | dict | Current device status (wavelength, absorbance, progress)| | 
| **scan_progress** | READ ONLY | float | Scan progress percentage (0-100)| | 

## Setup options:
| Name | Required | Type | Description |
|------|----------|------|-------------|
