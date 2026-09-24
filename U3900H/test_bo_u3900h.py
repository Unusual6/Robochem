"""
贝叶斯优化 (BO) 驱动 U3900H UV 光谱仪样例实验

目标: 验证 BO 算法能在闭环中正确驱动 U3900H 设备
- BO 变量: start_wavelength (190-1100 nm 连续)
- 目标函数: 最大化扫描范围内的最大吸光度
- 引擎: BoTorch (SingleTaskGP + Expected Improvement)
- 设备驱动: U3900HSpectrometer (TCP localhost:9000 -> 虚拟光谱仪)

运行前置: 虚拟光谱仪服务器 (e:\\workspace\\Robochem\\U3900H\\virtual_spectrometer_server.py) 已启动
"""
import os
import sys
import time
import math
import numpy as np
import pandas as pd
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from botorch.acquisition import ExpectedImprovement
from botorch.optim import optimize_acqf
from gpytorch.mlls import ExactMarginalLogLikelihood
import warnings

warnings.filterwarnings("ignore")

OMNIPLATYPUS_PATH = os.path.join(
    "e:\\workspace\\Robochem",
    "Control Software", "OmniPlatypus", "OmniPlatypus"
)
sys.path.insert(0, OMNIPLATYPUS_PATH)

from omniplatypus.devices.nrg.u3900h_spectrometer import U3900HSpectrometer


# ============== BO 配置 ==============
BOUNDS = (190.0, 1100.0)              # start_wavelength 物理范围
N_INIT = 4                             # 初始随机采样数
N_ITER = 6                             # BO 迭代次数
SCAN_SPAN = 200.0                      # 每次扫描覆盖 200 nm (start -> start - 200)
SCAN_SPEED = 600.0                     # nm/min (加速虚拟扫描)
DEVICE_HOST = "localhost"
DEVICE_PORT = 9100


def make_device() -> U3900HSpectrometer:
    """Create, open, initialize a U3900H device instance."""
    dev = U3900HSpectrometer()
    dev.open(DEVICE_HOST, DEVICE_PORT)
    dev.initialize()
    return dev


def run_one_experiment(dev: U3900HSpectrometer, start_wv: float) -> float:
    """Run a single scan on U3900H and return the max absorbance (objective)."""
    end_wv = max(start_wv - SCAN_SPAN, BOUNDS[0])  # scan towards shorter wavelengths
    if end_wv < BOUNDS[0]:
        end_wv = BOUNDS[0]

    print(f"  [DEV] Setting start={start_wv:.2f} nm, end={end_wv:.2f} nm, speed={SCAN_SPEED} nm/min")
    dev["start_wavelength"] = float(start_wv)
    dev["end_wavelength"] = float(end_wv)
    dev["scan_speed"] = float(SCAN_SPEED)

    # Trigger selftest (only once typically; do it anyway to validate path)
    # Baseline + scan
    print("  [DEV] Triggering baseline calibration ...")
    dev["baseline_calibrate"] = True

    print("  [DEV] Triggering scan ...")
    t0 = time.time()
    dev["start_scan"] = True
    scan_time = time.time() - t0

    data = dev["data"]
    if data is None or len(data) == 0:
        print(f"  [DEV] WARNING: no data returned")
        return float("-inf")

    max_abs = float(data["absorbance"].max())
    max_wv = float(data.loc[data["absorbance"].idxmax(), "wavelength"])
    print(f"  [DEV] Scan done in {scan_time:.1f}s | {len(data)} pts | max absorbance={max_abs:.4f} @ {max_wv:.1f} nm")
    return max_abs


def bo_suggest_next(train_x: torch.Tensor, train_y: torch.Tensor, bounds: torch.Tensor) -> torch.Tensor:
    """One step of BO: fit GP, build EI, optimize."""
    # GP needs double dtype and at least 2 points
    train_x = train_x.double()
    train_y = train_y.double().unsqueeze(-1)

    gp = SingleTaskGP(train_x, train_y)
    mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
    fit_gpytorch_mll(mll)

    ei = ExpectedImprovement(gp, best_f=train_y.max().item())
    candidate, _ = optimize_acqf(
        ei, bounds=bounds, q=1, num_restarts=10, raw_samples=64
    )
    return candidate


def main():
    print("="*72)
    print(" Bayesian Optimization driving U3900H UV-Vis Spectrometer ")
    print("="*72)
    print(f"BO variable: start_wavelength  range=[{BOUNDS[0]}, {BOUNDS[1]}] nm")
    print(f"Objective:  maximize peak absorbance over {SCAN_SPAN}-nm window")
    print(f"Initial points: {N_INIT}, BO iterations: {N_ITER}")
    print(f"Device: U3900HSpectrometer @ {DEVICE_HOST}:{DEVICE_PORT}")
    print("="*72)

    # Setup BoTorch bounds (shape: 2 x 1 for 1D problem)
    bounds_t = torch.tensor([[BOUNDS[0]], [BOUNDS[1]]], dtype=torch.double)

    # Open device ONCE; reuse across all BO iterations
    dev = make_device()
    print(f"[SETUP] Device open: {dev.is_open()}, initialized: {dev.is_initialized()}\n")

    # ---- Initial random sampling (Sobol for good space-filling) ----
    from botorch.utils.sampling import draw_sobol_samples
    init_x = draw_sobol_samples(bounds=bounds_t, n=N_INIT, q=1).squeeze(-1).double()
    print(f"[INIT] Sobol initial points: {[round(v.item(), 2) for v in init_x]}\n")

    train_x = init_x
    train_y = torch.empty(0, dtype=torch.double)

    for i, x0 in enumerate(init_x):
        wv = float(x0.item())
        print(f"[INIT {i+1}/{N_INIT}] start_wavelength = {wv:.2f} nm")
        y = run_one_experiment(dev, wv)
        train_y = torch.cat([train_y, torch.tensor([y], dtype=torch.double)])

    print(f"\n[INIT] Observed objectives: {[round(v, 4) for v in train_y.tolist()]}")
    print(f"[INIT] Best so far: y_max = {train_y.max().item():.4f}\n")

    # ---- BO iterations ----
    for it in range(N_ITER):
        print("-"*60)
        print(f"[BO iter {it+1}/{N_ITER}] Fitting GP + EI ...")
        next_x = bo_suggest_next(train_x, train_y, bounds_t)
        wv = float(next_x.item())
        print(f"[BO iter {it+1}] Suggested start_wavelength = {wv:.2f} nm")
        y = run_one_experiment(dev, wv)

        train_x = torch.cat([train_x, next_x])
        train_y = torch.cat([train_y, torch.tensor([y], dtype=torch.double)])

        print(f"[BO iter {it+1}] Observed y = {y:.4f} | Best so far = {train_y.max().item():.4f}")

    # ---- Summary ----
    print("\n" + "="*72)
    print(" BO Experiment Summary ")
    print("="*72)
    print(f"Total evaluations: {len(train_y)} ({N_INIT} init + {N_ITER} BO)")
    best_idx = int(train_y.argmax().item())
    print(f"Best objective:  y_max = {train_y[best_idx].item():.4f}")
    print(f"Best start_wavelength: {train_x[best_idx].item():.2f} nm")
    print("\nAll evaluations:")
    print(f"  {'iter':<6}{'start_wavelength (nm)':<24}{'max_absorbance':<18}")
    for i, (x, y) in enumerate(zip(train_x, train_y)):
        flag = " <-- best" if i == best_idx else ""
        print(f"  {i+1:<6}{x.item():<24.2f}{y.item():<18.4f}{flag}")
    print("="*72)

    dev.close()
    print("[DONE] Device closed.")


if __name__ == "__main__":
    main()
