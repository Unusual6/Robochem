"""
U3900H 驱动基础闭环测试
验证: open -> initialize -> selftest -> baseline -> scan -> read data
"""
import sys
import time
import os

# Add OmniPlatypus to path
OMNIPLATYPUS_PATH = os.path.join(
    "e:\\workspace\\Robochem",
    "Control Software", "OmniPlatypus", "OmniPlatypus"
)
sys.path.insert(0, OMNIPLATYPUS_PATH)

from omniplatypus.devices.nrg.u3900h_spectrometer import U3900HSpectrometer


def main():
    dev = U3900HSpectrometer()
    print(f"[TEST] Built device: {dev.generic_name}")
    print(f"[TEST] Parameters: {[p.name for p in dev.parameters()]}")

    # 1. Open connection
    print("\n[STEP 1] Opening TCP connection to localhost:9100 ...")
    dev.open("localhost", 9100)
    print(f"[STEP 1] is_open={dev.is_open()}")

    # 2. Initialize (sets _initialized=True so writes are allowed)
    print("\n[STEP 2] Initializing device ...")
    dev.initialize()
    print(f"[STEP 2] is_initialized={dev.is_initialized()}")

    # 3. Set scan parameters BEFORE selftest (selftest sends method params)
    print("\n[STEP 3] Setting scan parameters ...")
    dev["start_wavelength"] = 534.0
    dev["end_wavelength"] = 200.0
    dev["scan_speed"] = 300.0
    print(f"[STEP 3] start={dev['start_wavelength']}, end={dev['end_wavelength']}, speed={dev['scan_speed']}")

    # 4. Trigger selftest
    print("\n[STEP 4] Triggering selftest ...")
    t0 = time.time()
    dev["selftest"] = True
    print(f"[STEP 4] Selftest done in {time.time()-t0:.1f}s")

    # 5. Trigger baseline calibration
    print("\n[STEP 5] Triggering baseline calibration ...")
    t0 = time.time()
    dev["baseline_calibrate"] = True
    print(f"[STEP 5] Baseline done in {time.time()-t0:.1f}s")

    # 6. Trigger scan
    print("\n[STEP 6] Triggering scan (534 -> 200 nm) ...")
    t0 = time.time()
    dev["start_scan"] = True
    print(f"[STEP 6] Scan done in {time.time()-t0:.1f}s")

    # 7. Read data
    print("\n[STEP 7] Reading scan data ...")
    data = dev["data"]
    if data is None:
        print("[STEP 7] No data returned!")
    else:
        print(f"[STEP 7] Data shape: {data.shape}")
        print(f"[STEP 7] Columns: {list(data.columns)}")
        print(f"[STEP 7] First 5 rows:\n{data.head()}")
        print(f"[STEP 7] Last 5 rows:\n{data.tail()}")
        print(f"[STEP 7] Max absorbance: {data['absorbance'].max():.4f} at wavelength {data.loc[data['absorbance'].idxmax(), 'wavelength']:.2f} nm")
        print(f"[STEP 7] Min absorbance: {data['absorbance'].min():.4f}")

    # 8. Status
    print("\n[STEP 8] Reading status ...")
    status = dev["status"]
    print(f"[STEP 8] Status: {status}")

    # 9. Close
    print("\n[STEP 9] Closing device ...")
    dev.close()
    print("[TEST] Done.")


if __name__ == "__main__":
    main()
