"""
基于 ramanspy 的光谱解混算法 (nowdata 数据)
=============================================
解混核心基于 ramanspy, 展示图例与 UgiSDK 完全一致 (通过继承复用绘图方法):

  1. 校准      — 各组分多浓度标准谱 → 缩放系数 → 校准曲线 R² (与 UgiSDK 相同)
  2. PCA 背景  — nowdata/pca 纯 MeCN 背景谱 → sklearn PCA → 背景分量
  3. 解混      — ramanspy 算法:
       * 基线估计:   ramanspy.preprocessing.baseline.ARPLS
       * 丰度求解:   ramanspy.analysis.unmix.amaps.{NNLS, UCLS, FCLS}
       * PCA 背景权重: 残差最小二乘投影 (允许负权重)
  4. 换算      — 丰度系数 → 校准曲线插值 → 浓度 + 不确定度
  5. 绘图      — 与 UgiSDK 相同: fig_calibration_*, fig_pca_background_analysis,
                 fig_unmix_* (含残差与 PCA 各分量放大), fig_concentration_verification

数据目录:
  - nowdata/pca/  : 纯 MeCN 背景谱 (PCA 背景建模)
  - nowdata/chem/ : 标准谱 (校准) 与混合谱 (解混)

依赖: ramanspy, pysptools, numpy, scipy, scikit-learn, matplotlib
"""

import numpy as np
import os
import sys
import io
import glob
from typing import Dict, List, Optional, Tuple

# 修复 Windows 控制台编码 (幂等)
if sys.stdout.encoding is None or 'utf-8' not in sys.stdout.encoding.lower():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ramanspy 解混核心
import ramanspy
from ramanspy.analysis.unmix import amaps as raman_amaps
from ramanspy.preprocessing.baseline import ARPLS

from UgiSDK import UgiSDK, UnmixResult

# ============================================================
# 主 SDK 类 — 继承 UgiSDK 复用全部图例, 替换解混算法为 ramanspy
# ============================================================
class RamanspyUnmixSDK(UgiSDK):
    """
    基于 ramanspy 的光谱解混 SDK

    继承 UgiSDK 的校准 / PCA 背景 / 绘图方法, 保证图例样式完全一致;
    仅替换解混核心算法:

      模型: A(i) = Σⱼ aⱼ·Rⱼ(i) + B_arpls(i) + b₀ + b₁·i + Σₖ wₖ·PCₖ(i)

      - aⱼ       : ramanspy 丰度求解 (NNLS 非负 / UCLS 无约束 / FCLS 全约束)
      - B_arpls  : ramanspy ARPLS 基线估计
      - b₀, b₁   : 偏移 + 线性漂移 (最小二乘投影)
      - wₖ       : PCA 背景权重 (最小二乘投影, 允许负值)

    Parameters
    ----------
    data_dir : str
        光谱数据目录
    method : str
        ramanspy 丰度方法: "NNLS" (推荐), "UCLS", "FCLS"
    arpls_lam : float
        ARPLS 基线平滑参数
    use_arpls_baseline : bool
        是否启用 ramanspy ARPLS 基线校正。注意: ARPLS 面向拉曼窄峰设计,
        对 UV-Vis 宽峰吸收谱会过度扣除, 默认关闭; 拉曼类数据可设为 True。
    """

    def __init__(
        self,
        data_dir: str = "data",
        skip_rows: int = 36,
        tail_points: int = 100,
        reverse_order: bool = True,
        method: str = "NNLS",
        arpls_lam: float = 1e5,
        use_arpls_baseline: bool = False,
    ):
        super().__init__(
            data_dir=data_dir,
            skip_rows=skip_rows,
            tail_points=tail_points,
            reverse_order=reverse_order,
        )
        self.method = method.upper()
        self.arpls_lam = arpls_lam
        self.use_arpls_baseline = use_arpls_baseline

    # ============================================================
    # ramanspy 基线校正
    # ============================================================
    def _ramanspy_baseline(self, spectrum: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        基于 ramanspy ARPLS 估计基线

        Parameters
        ----------
        spectrum : ndarray, shape (n_wl,)

        Returns
        -------
        (corrected, baseline) : (ndarray, ndarray)
            校正后光谱, 基线光谱
        """
        sd = ramanspy.Spectrum(spectrum.copy(), self.wavelength)
        corrected = ARPLS(lam=self.arpls_lam).apply(sd).spectral_data
        baseline = spectrum - corrected
        return np.asarray(corrected, dtype=float), np.asarray(baseline, dtype=float)

    # ============================================================
    # 解混核心 (ramanspy)
    # ============================================================
    def unmix_spectrum(
        self,
        mixture_spectrum: np.ndarray,
        sample_name: str = "unknown",
        true_concentrations: Optional[Dict[str, float]] = None,
        ignore_pca_bkg: bool = False,
        use_line: bool = True,
        dilution_factor: float = 1.0,
    ) -> UnmixResult:
        """
        解混单个混合光谱 (ramanspy 算法)

        Parameters
        ----------
        mixture_spectrum : ndarray
            混合光谱 (原始, 未扣背景)
        sample_name : str
            样品名称
        true_concentrations : dict, optional
            真实浓度 {组分名: 浓度}
        ignore_pca_bkg : bool
            是否忽略 PCA 背景分量
        use_line : bool
            是否拟合线性基线漂移
        dilution_factor : float
            稀释因子 (乘到最终浓度上)

        Returns
        -------
        UnmixResult
        """
        if true_concentrations is None:
            true_concentrations = {}

        n_comp = len(self._component_names)
        wl_idx = self._wavelength_indices

        # ---- 扣背景 ----
        if self._bg_spectrum is not None:
            mix_bkg_sub = mixture_spectrum - self._bg_spectrum
        else:
            mix_bkg_sub = mixture_spectrum.copy()

        # ---- 尾基线校正 ----
        mix_for_fit = mix_bkg_sub.copy()
        if self.tail_points > 0:
            mix_for_fit -= np.mean(mix_for_fit[-self.tail_points:])

        # ---- ramanspy ARPLS 基线 ----
        if self.use_arpls_baseline:
            arpls_corrected, arpls_baseline = self._ramanspy_baseline(mix_for_fit)
        else:
            arpls_corrected = mix_for_fit.copy()
            arpls_baseline = np.zeros_like(mix_for_fit)

        # ---- 组分矩阵 (各组分参考谱, 尾基线校正后) ----
        ref_matrix = np.column_stack([
            self._calibrations[name].ref_spectrum for name in self._component_names
        ])  # (n_wl, n_comp)

        # ---- ramanspy 丰度求解 ----
        M = arpls_corrected.reshape(1, -1)       # (1, n_wl)
        E = ref_matrix.T                         # (n_comp, n_wl)

        if self.method == "NNLS":
            abund = raman_amaps.NNLS(M, E).flatten()
        elif self.method == "UCLS":
            abund = raman_amaps.UCLS(M, E).flatten()
        elif self.method == "FCLS":
            abund = raman_amaps.FCLS(M, E).flatten()
        else:
            raise ValueError(
                f"不支持的 ramanspy 方法: {self.method}, 可选: NNLS, UCLS, FCLS"
            )

        a_vals = np.maximum(abund, 0.0)          # 浓度系数 (丰度), 钳制负值

        # ---- 残差: 偏移 + 线性漂移 + PCA 背景权重 ----
        residual_after = arpls_corrected - ref_matrix @ a_vals
        fit_cols = []
        fit_names = ['baseline_offset']
        fit_cols.append(np.ones(len(wl_idx)))
        if use_line:
            fit_cols.append(wl_idx)
            fit_names.append('linear_drift')
        if self._pca_result is not None and not ignore_pca_bkg:
            for k in range(self._pca_result.n_components):
                fit_cols.append(self._pca_result.components[:, k])
                fit_names.append(f'pca_{k}')
        if fit_cols:
            F = np.column_stack(fit_cols)
            pfit, _, _, _ = np.linalg.lstsq(F, residual_after, rcond=None)
        else:
            pfit = np.zeros(len(fit_names))

        # ---- 组装拟合光谱 ----
        base_offset = float(pfit[0])
        linear_drift = float(pfit[1]) if use_line else 0.0
        pca_weights = {}
        pca_comp_contribs = {}
        n_pca = len(fit_names) - (2 if use_line else 1)
        pca_contrib = np.zeros(len(wl_idx))
        if n_pca > 0:
            pca_start = 2 if use_line else 1
            for k in range(n_pca):
                w = float(pfit[pca_start + k])
                pca_weights[f'pca_{k}'] = w
                comp_contrib = w * self._pca_result.components[:, k]
                pca_comp_contribs[f'pca_{k}'] = comp_contrib
                pca_contrib += comp_contrib

        baseline_spectrum = arpls_baseline + base_offset + linear_drift * wl_idx
        fitted_bkg_sub = (
            ref_matrix @ a_vals + arpls_baseline
            + base_offset + linear_drift * wl_idx + pca_contrib
        )

        # ---- 拟合光谱 (未扣背景坐标系) ----
        fitted_spectrum = fitted_bkg_sub + (
            self._bg_spectrum if self._bg_spectrum is not None else 0
        )

        # ---- 残差 / R² / RMSE ----
        residual = mix_bkg_sub - fitted_bkg_sub
        ss_res = np.sum(residual ** 2)
        ss_tot = np.sum((mix_for_fit - np.mean(mix_for_fit)) ** 2)
        r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 1.0
        rmse = float(np.sqrt(np.mean(residual ** 2)))

        # 置信度
        if r2 >= 0:
            raw = 1.0 - np.exp(-10 * max(r2 - 0.9, 0)) * (1 - r2 + 0.01)
            confidence = float(max(0.0, min(1.0, raw)))
        else:
            confidence = 0.0

        # ---- 浓度换算 (校准曲线插值, 同 UgiSDK) ----
        concentrations = {}
        conc_errors = {}
        scaling_coeffs = {}
        coeff_errs = {}

        for i, name in enumerate(self._component_names):
            cal = self._calibrations[name]
            coeff = a_vals[i]
            # ramanspy NNLS 不提供协方差, 用组分贡献残差近似估计不确定度
            contrib = coeff * cal.ref_spectrum
            contrib_resid = residual_after - sum(
                (0.0 if k == i else a_vals[k]) * self._calibrations[n].ref_spectrum
                for k, n in enumerate(self._component_names)
            )
            # 简化: 用该组分贡献的 RMSE 归一化系数作为误差
            if np.max(np.abs(contrib)) > 0:
                err_coeff = float(np.sqrt(np.mean(contrib_resid ** 2))) / max(
                    np.max(np.abs(contrib)), 1e-30
                ) * abs(coeff)
            else:
                err_coeff = 0.0

            cal_coeffs = np.array(cal.coefficients)
            cal_concs = np.array(cal.concentrations)
            if len(cal_coeffs) >= 2 and np.std(cal_coeffs) > 0:
                conc = float(np.interp(coeff, cal_coeffs, cal_concs))
                conc_up = float(np.interp(coeff + err_coeff, cal_coeffs, cal_concs))
                conc_lo = float(np.interp(coeff - err_coeff, cal_coeffs, cal_concs))
                conc_err = abs(conc_up - conc_lo) / 2.0
            else:
                conc = coeff * cal.ref_concentration
                conc_err = err_coeff * cal.ref_concentration

            conc *= dilution_factor
            conc_err *= dilution_factor
            concentrations[name] = conc
            conc_errors[name] = conc_err
            scaling_coeffs[name] = float(coeff)
            coeff_errs[name] = float(err_coeff)

        # ---- 各组分贡献谱 ----
        contributions = {}
        for i, name in enumerate(self._component_names):
            contributions[name] = a_vals[i] * self._calibrations[name].ref_spectrum

        result = UnmixResult(
            sample_name=sample_name,
            concentrations=concentrations,
            concentration_errors=conc_errors,
            true_concentrations=true_concentrations,
            r2=r2,
            rmse=rmse,
            confidence=confidence,
            mixture_spectrum=mixture_spectrum.copy(),
            background_subtracted=mix_bkg_sub.copy(),
            fitted_spectrum=fitted_spectrum,
            residual=residual,
            component_contributions=contributions,
            baseline_spectrum=baseline_spectrum,
            pca_contribution=pca_contrib,
            pca_weights=pca_weights,
            scaling_coefficients=scaling_coeffs,
            coeff_errors=coeff_errs,
            pca_component_contributions=pca_comp_contribs,
        )
        self._results.append(result)
        return result


# ============================================================
# nowdata 数据配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHEM_DIR = os.path.join(BASE_DIR, "nowdata", "chem")
PCA_DIR = os.path.join(BASE_DIR, "nowdata", "pca")
FIG_DIR = os.path.join(BASE_DIR, "figs_nowdata_ramanspy")

SKIP_ROWS = 36

REFERENCE_FILES = {
    "DMSO": {
        "UV-1-DMSO_0.000075(MeCN).TXT": 0.000075,
        "UV-1-DMSO_0.0002065(MeCN).TXT": 0.0002065,
        "UV-1-DMSO_0.000413(MeCN).TXT": 0.000413,
        "UV-1-DMSO_0.000826(MeCN).TXT": 0.000826,
    },
    "DPB": {
        "UV-1-DPB_0.00001875(MeCN).TXT": 0.00001875,
        "UV-1-DPB_0.0000375(MeCN).TXT": 0.0000375,
        "UV-1-DPB_0.000075(MeCN).TXT": 0.000075,
    },
}

MIXTURE_FILES = {
    "UV-1-DPB_0.00000938&DMSO_0.0001033(MeCN).TXT": {
        "DPB": 0.00000938, "DMSO": 0.0001033
    },
    "UV-1-DPB_0.00001875&DMSO_0.0002065(MeCN).TXT": {
        "DPB": 0.00001875, "DMSO": 0.0002065
    },
}

BACKGROUND_FILE = "UV-1-MeCN(pure).TXT"
REF_CONCENTRATIONS = {"DMSO": 0.000413, "DPB": 0.0000375}
N_PCA_COMPONENTS = 3


def load_background_spectra(pca_dir: str, skip_rows: int = 36) -> np.ndarray:
    """读取 pca 目录下所有纯溶剂背景谱 (与 SDK 相同: 反转波长排列)"""
    files = sorted(glob.glob(os.path.join(pca_dir, "*.TXT")))
    spectra = []
    for f in files:
        data = np.loadtxt(f, skiprows=skip_rows)
        wl, inten = data[:, 0], data[:, 1]
        spectra.append(inten[::-1])
    print(f"  PCA 背景谱数量: {len(spectra)}")
    return np.array(spectra)


def main():
    import sys as _sys
    method = _sys.argv[1].upper() if len(_sys.argv) > 1 else "NNLS"
    if method not in ("NNLS", "UCLS", "FCLS"):
        print(f"不支持的方法: {method}, 使用默认 NNLS")
        method = "NNLS"

    os.makedirs(FIG_DIR, exist_ok=True)
    sdk = RamanspyUnmixSDK(data_dir=CHEM_DIR, skip_rows=SKIP_ROWS, method=method)

    print("=" * 72)
    print(f"ramanspy 解混 (nowdata) — 方法: {method}")
    print("=" * 72)

    print("\n>>> 步骤 1: 校准各组分 (nowdata/chem 标准谱)...")
    cals = sdk.calibrate_all(REFERENCE_FILES, BACKGROUND_FILE, REF_CONCENTRATIONS)
    for name, cal in cals.items():
        print(
            f"  {name}: 参考浓度={cal.ref_concentration:.6e}, "
            f"校准 R²={cal.overall_r2:.6f}, "
            f"拟合 R²={cal.calibration_r2:.6f}"
        )

    print("\n>>> 步骤 2: PCA 背景分析 (nowdata/pca)...")
    bg_spectra = load_background_spectra(PCA_DIR, SKIP_ROWS)
    pca = sdk.pca_background_analysis(
        background_spectra=bg_spectra, n_components=N_PCA_COMPONENTS
    )
    if pca:
        print(f"  主成分数: {pca.n_components}")
        print(f"  重构 RMSE: {pca.reconstruction_error:.6f}")
        for i in range(pca.n_components):
            print(
                f"  PC{i + 1}: 方差解释="
                f"{pca.explained_variance_ratio[i] * 100:.2f}%, "
                f"累积={pca.cumulative_variance[i] * 100:.2f}%"
            )

    print(f"\n>>> 步骤 3: ramanspy 解混混合样品 ({method})...")
    results = sdk.unmix_all(MIXTURE_FILES, use_line=True)
    for r in results:
        print(f"\n  样品: {r.sample_name}")
        print(
            f"    R² = {r.r2:.6f}, RMSE = {r.rmse:.6f}, "
            f"置信度 = {r.confidence:.2%}"
        )
        for name in sdk.component_names:
            conc = r.concentrations[name]
            unc = r.concentration_errors[name]
            true_c = r.true_concentrations.get(name)
            err_pct = r.errors_pct.get(name)
            if true_c is not None and err_pct is not None:
                print(
                    f"    {name}: {conc:.6e}±{unc:.6e} "
                    f"(真实={true_c:.6e}, Δ={err_pct:.2f}%)"
                )
            else:
                print(f"    {name}: {conc:.6e}±{unc:.6e}")

    print("\n>>> 完整报告:")
    sdk.print_report()

    print("\n>>> 绘制图表 (与 UgiSDK 相同样式)...")
    sdk.plot_all(FIG_DIR)
    print(f"  图表已保存到: {FIG_DIR}")

    return sdk, results


if __name__ == "__main__":
    main()
