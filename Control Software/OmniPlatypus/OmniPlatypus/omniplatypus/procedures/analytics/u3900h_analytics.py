"""
Author: Robochem U3900H Integration

Descr: Analytics class for Hitachi U-3900H UV-Vis Spectrometer.
       Handles scan acquisition, spectral unmixing (NNLS) of the mixture spectrum
       into pure-component concentrations, and yield calculation.

       Yield is computed from the unmixed product concentration, the dilution factor
       configured in the frontend, the stoichiometric coefficients of the reaction
       equation and the concentration of the controlled (limiting) reactant in the recipe:

           yield = (c_product_unmixed * dilution_factor) /
                   (c_controlled_reactant * (nu_product / nu_reactant))

       The unmixing calibration is provided via 'path_to_calibration_file', a JSON file
       listing pure-component reference spectra (with their concentrations in mol/L)
       and an optional background (pure solvent) spectrum. See
       unmix/nowdata/chem/calibration.json for the expected format.
"""

import json
import os.path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

from omniplatypus.devices.nrg.u3900h_spectrometer import U3900HSpectrometer
from omniplatypus.procedures.unit_tasks.sampling.liquid_handler_sampling import (
    RecipeComponent,
)
from omniplatypus.procedures.experiments.experiment_parameters import (
    ExperimentalParameter,
    NumericalParameter,
)
from omniplatypus.procedures.analytics.analytics_parameters import AnalyticalParameter
from omniplatypus.procedures.analytics.analytics_template import (
    AnalyticsTemplate,
    AnalysisError,
)

# Concentration units of the recipe (see RecipeComponent.concentration_units)
_CONCENTRATION_UNITS = "mM"


def _load_spectrum_file(file_path: str) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Load a wavelength/absorbance spectrum from a U3900H TXT export file.

    The parser is robust against the file header (instrument parameters etc.):
    any line which does not start with two floats is skipped.

    @param file_path: str
        Path to the TXT file.
    @return: tuple[np.ndarray, np.ndarray] | None
        (wavelengths ascending, absorbances) or None if the file could not be read.
    """
    wavelengths = []
    absorbances = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            for line in file:
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    wavelength = float(parts[0])
                    absorbance = float(parts[1])
                except ValueError:
                    continue
                wavelengths.append(wavelength)
                absorbances.append(absorbance)
    except OSError:
        return None
    if not wavelengths:
        return None
    wavelengths = np.asarray(wavelengths, dtype=float)
    absorbances = np.asarray(absorbances, dtype=float)
    order = np.argsort(wavelengths)
    return wavelengths[order], absorbances[order]


class AnalyticsU3900H(AnalyticsTemplate):
    """
    UV-Vis Analysis class for Hitachi U-3900H spectrometer.

    Supports wavelength scanning and spectral unmixing of the acquired spectrum into
    pure-component concentrations (non-negative least squares, following the
    unmix/nowdata reference implementation).
    Processing methods: spectral_unmixing, single_point_absorbance, integrated_absorbance
    """

    _base_data = os.path.join("uv_spectra")
    result_metrics: list[str] = [
        "yield",
        "integral",
        "integral_starting_material",
        "absorbance_at_wlen",
        "pass",
    ]

    _required_parameters: list[AnalyticalParameter] = [
        AnalyticalParameter(
            name="yield_calculation_chemical",
            value="",
            tag="all",
        ),
        AnalyticalParameter(
            name="start_wavelength",
            value=534.0,
            min_value=190.0,
            max_value=1100.0,
            units="nm",
            tag="all",
        ),
        AnalyticalParameter(
            name="end_wavelength",
            value=200.0,
            min_value=190.0,
            max_value=1100.0,
            units="nm",
            tag="all",
        ),
        AnalyticalParameter(
            name="scan_speed",
            value=300.0,
            min_value=1.0,
            max_value=3000.0,
            units="nm/min",
            tag="all",
        ),
        AnalyticalParameter(name="sample_name", value="test"),
        AnalyticalParameter(
            name="data_folder",
            value=os.path.join("Path", "To", "Data", "Folder"),
        ),
    ]

    _optional_parameters: list[AnalyticalParameter] = [
        AnalyticalParameter(
            name="baseline_calibrate",
            value=True,
            tag="all",
        ),
        AnalyticalParameter(
            name="integration_lower_bound",
            value=200,
            min_value=190,
            max_value=1100,
            units="nm",
            tag="simple_integration",
        ),
        AnalyticalParameter(
            name="integration_upper_bound",
            value=600,
            min_value=190,
            max_value=1100,
            units="nm",
            tag="simple_integration",
        ),
        AnalyticalParameter(
            name="molar_extinction_coefficient",
            value=1.0,
            min_value=0.0,
            max_value=1.0e50,
            units="L/(mol*cm)",
            tag="all",
        ),
        AnalyticalParameter(
            name="path_to_calibration_file",
            value="",
            tag="all",
        ),
        # ---- spectral unmixing parameters ----
        # Name of the product component in the calibration file whose unmixed
        # concentration is used for the yield calculation.
        AnalyticalParameter(
            name="product_chemical",
            value="",
            tag="all",
        ),
        # Dilution factor applied to the sample between reactor and measurement.
        AnalyticalParameter(
            name="dilution_factor",
            value=1.0,
            min_value=0.0,
            units="",
            tag="all",
        ),
        # Stoichiometric coefficients of the reaction equation:
        # nu_reactant * controlled reactant -> nu_product * product
        AnalyticalParameter(
            name="stoichiometry_product_coefficient",
            value=1.0,
            min_value=1.0e-12,
            units="",
            tag="all",
        ),
        AnalyticalParameter(
            name="stoichiometry_reactant_coefficient",
            value=1.0,
            min_value=1.0e-12,
            units="",
            tag="all",
        ),
    ]

    _processing_methods = [
        "spectral_unmixing",
        "single_point_absorbance",
        "integrated_absorbance",
    ]

    def analyse(
        self,
        conditions: dict[
            str, ExperimentalParameter | NumericalParameter | AnalyticalParameter
        ],
        recipe: list[RecipeComponent],
        process_only: bool = False,
    ) -> dict:
        """
        Run UV-Vis analysis using the U3900H spectrometer.

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        @param recipe: list[RecipeComponent]
            Chemical conditions, reagents and their concentrations (in mM).
        @param process_only: bool = False
            If true, skip acquisition and process existing data.
        @return: dict
            Results dictionary with yield, integral, absorbance, pass/fail.
        """
        _parameters = self.validate_parameters(conditions)
        non_spectrometer_parameters = self._split_parameters(_parameters)

        if not process_only:
            self._set_parameters(conditions)
            data = self._spectrometer_run()
        else:
            data_file = os.path.join(
                non_spectrometer_parameters.get("experiment_path", {}).get("value", ""),
                non_spectrometer_parameters.get("experiment_name", {}).get("value", ""),
            )
            data = self.read_data(data_file)

        metrics = self._process_analytics(
            data=data,
            recipe=recipe,
            non_spectrometer_parameters=non_spectrometer_parameters,
            conditions=conditions,
        )

        results = self._make_results(
            metrics=metrics, recipe=recipe, conditions=conditions
        )

        if not process_only:
            self._save_spectrum(data=data, conditions=conditions)

        return results

    def _save_spectrum(
        self,
        data: pd.DataFrame | None,
        conditions: dict[
            str, ExperimentalParameter | NumericalParameter | AnalyticalParameter
        ],
    ) -> None:
        """Store the acquired spectrum as CSV in the analysis raw data folder."""
        if data is None or data.empty:
            return
        try:
            sample_name = conditions["sample_name"].value
            destination_folder = os.path.join(self._storage_root, "raw_data_analysis")
            if not os.path.isdir(destination_folder):
                os.mkdir(destination_folder)
            destination = os.path.join(
                destination_folder, str(sample_name) + ".csv"
            )
            data.to_csv(destination, index=False)
            self.log(f"Saved spectrum '{destination}'.")
        except Exception as error:
            self.log(f"Failed to save spectrum, non-fatal: {error}", level="error")

    def _set_parameters(
        self,
        conditions: dict[
            str, ExperimentalParameter | NumericalParameter | AnalyticalParameter
        ],
    ):
        """Set spectrometer parameters from conditions."""
        self.log("Setting U3900H parameters", indent="enter")

        self._device["start_wavelength"] = conditions["start_wavelength"].value
        self._device["end_wavelength"] = conditions["end_wavelength"].value
        self._device["scan_speed"] = conditions["scan_speed"].value

        self.log("U3900H parameters set successfully", level="ok", indent="exit")

    def _spectrometer_run(self) -> pd.DataFrame | None:
        """
        Run baseline calibration (if needed) and a wavelength scan.
        Returns scan data as DataFrame.
        """
        self.log("Starting U3900H acquisition", indent="enter")

        # Run self-test first to initialize
        self.log("Running self-test...")
        self._device["selftest"] = True
        import time

        time.sleep(2)

        # Run baseline calibration
        self.log("Running baseline calibration...")
        self._device["baseline_calibrate"] = True
        time.sleep(2)

        # Start scan
        self.log("Starting scan acquisition...")
        self._device["start_scan"] = True
        time.sleep(1)

        # Poll data
        data = self._spectrometer_poll()

        self.log("Acquisition finished", indent="exit")

        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            self.log("No data returned from U3900H", level="error")
            raise AnalysisError("No data was returned from U3900H")

        return data

    def _spectrometer_poll(self) -> pd.DataFrame | None:
        """Poll scan data from the spectrometer."""
        self.log("Polling U3900H data", indent="enter")

        # Wait for scan to complete by polling progress
        max_wait = 60  # seconds
        waited = 0
        while waited < max_wait:
            progress = self._device["scan_progress"]
            if progress >= 100.0:
                break
            import time

            time.sleep(0.5)
            waited += 0.5

        data = self._device["data"]
        self.log("Data polled successfully", indent="exit")
        return data

    def read_data(self, file_path: str) -> pd.DataFrame | None:
        """Read data from a CSV file."""
        if file_path and os.path.exists(file_path):
            return pd.read_csv(file_path)
        return None

    def _split_parameters(
        self, _parameters: dict[str, AnalyticalParameter]
    ) -> dict:
        """Split parameters by processing method tag."""
        self.log("Splitting parameters", indent="enter")
        all_parameters = {}
        integration_parameters = {}

        _integral_parameters = [
            param.name
            for param in (self._required_parameters + self._optional_parameters)
            if param.tag == "simple_integration"
        ]
        _all_parameters = [
            param.name
            for param in (self._required_parameters + self._optional_parameters)
            if param.tag == "all"
        ]

        for param_key, param_value in _parameters.items():
            if not isinstance(param_value, AnalyticalParameter):
                continue
            if param_key in _all_parameters:
                all_parameters[param_key] = param_value
            elif param_key in _integral_parameters:
                integration_parameters[param_key] = param_value
            else:
                self.log(
                    f"Parameter {param_key} has no recognized tag, skipping",
                    level="warning",
                )

        self.log("Parameters split successfully", indent="exit", level="ok")
        return {
            "all": all_parameters,
            "simple_integration": integration_parameters,
        }

    # ==================== spectral unmixing ====================

    def _load_calibration(self, calibration_path: str) -> dict | None:
        """
        Load the unmixing calibration from a JSON file.

        The JSON format is (file paths relative to the JSON location):
        {
            "background_file": "UV-1-MeCN(pure).TXT",
            "reference_spectra": {
                "DPB": {"UV-1-DPB_0.0000375(MeCN).TXT": 3.75e-05, ...},
                ...
            }
        }

        For each component, the highest-concentration reference spectrum is used
        as the basis. A calibration curve (scaling coefficient -> concentration,
        including the origin) is built by fitting each reference file to the basis
        spectrum with a constant offset (least squares).

        @param calibration_path: str
            Path to the calibration JSON file.
        @return: dict | None
            {"background": (wl, abs) | None,
             "references": {name: {"wl", "abs", "ref_conc", "cal_coeffs", "cal_concs"}}}
            or None if the calibration could not be loaded.
        """
        if not calibration_path or not os.path.isfile(calibration_path):
            self.log(
                f"Calibration file not found: '{calibration_path}'",
                level="warning",
            )
            return None

        try:
            with open(calibration_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            self.log(f"Failed to read calibration file: {error}", level="error")
            return None

        base_dir = os.path.dirname(os.path.abspath(calibration_path))

        background = None
        background_file = config.get("background_file")
        if background_file:
            loaded = _load_spectrum_file(os.path.join(base_dir, background_file))
            if loaded is not None:
                background = loaded
            else:
                self.log(
                    f"Background spectrum '{background_file}' could not be loaded.",
                    level="warning",
                )

        references: dict[str, dict] = {}
        for name, spectra_files in config.get("reference_spectra", {}).items():
            spectra: dict[str, tuple[float, np.ndarray, np.ndarray]] = {}
            for file_name, concentration in spectra_files.items():
                if not concentration or concentration <= 0.0:
                    continue
                spectrum = _load_spectrum_file(os.path.join(base_dir, file_name))
                if spectrum is None:
                    self.log(
                        f"Reference spectrum '{file_name}' not found, skipping.",
                        level="warning",
                    )
                    continue
                wavelengths, absorbances = spectrum
                if background is not None:
                    absorbances = absorbances - np.interp(
                        wavelengths, background[0], background[1]
                    )
                spectra[file_name] = (float(concentration), wavelengths, absorbances)
            if not spectra:
                self.log(
                    f"No valid reference spectra for component '{name}', skipping.",
                    level="warning",
                )
                continue

            # Basis: highest-concentration reference spectrum.
            basis_name = max(spectra, key=lambda key: spectra[key][0])
            ref_conc, ref_wl, ref_ab = spectra[basis_name]

            # Calibration curve (coefficient -> concentration), including the
            # origin: each file is fitted to the basis spectrum with an offset.
            cal_coeffs = [0.0]
            cal_concs = [0.0]
            design = np.column_stack([ref_ab, np.ones(len(ref_ab))])
            for file_name, (concentration, wavelengths, absorbances) in spectra.items():
                target = np.interp(ref_wl, wavelengths, absorbances)
                coefficient, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
                cal_coeffs.append(float(coefficient[0]))
                cal_concs.append(concentration)
            order = np.argsort(cal_coeffs)
            references[name] = {
                "wl": ref_wl,
                "abs": ref_ab,
                "ref_conc": ref_conc,
                "cal_coeffs": np.asarray(cal_coeffs, dtype=float)[order],
                "cal_concs": np.asarray(cal_concs, dtype=float)[order],
            }
            self.log(
                f"Loaded calibration for '{name}' "
                f"({len(spectra)} reference spectra, basis concentration "
                f"{ref_conc:.3e} mol/L)."
            )

        if not references:
            return None
        return {"background": background, "references": references}

    def _unmix_spectrum(self, data: pd.DataFrame, calibration: dict) -> dict:
        """
        Unmix a mixture spectrum into pure-component concentrations.

        The background-subtracted mixture is modelled as:
            A(wl) = sum_j k_j * S_j(wl) + offset,  k_j >= 0
        where S_j is the highest-concentration reference spectrum of component j.
        The problem is solved with bounded linear least squares (lsq_linear):
        component coefficients are non-negative, the constant offset column is
        unconstrained.

        Concentrations are obtained by interpolating the coefficients on each
        component's calibration curve (which includes the origin); if the curve
        is degenerate (fewer than 2 distinct points), the coefficient is scaled
        by the basis concentration.

        @param data: pd.DataFrame
            Mixture spectrum (columns: wavelength, absorbance).
        @param calibration: dict
            Calibration as returned by _load_calibration.
        @return: dict
            {"concentrations": {name: mol/L}, "r2": float,
             "contributions": {name: ndarray}, "relative_error": float}
        """
        wavelengths = data.iloc[:, 0].to_numpy(dtype=float)
        absorbances = data.iloc[:, 1].to_numpy(dtype=float)

        background = calibration["background"]
        if background is not None:
            mixture = absorbances - np.interp(
                wavelengths, background[0], background[1]
            )
        else:
            mixture = absorbances.copy()

        names = list(calibration["references"].keys())
        reference_matrix = np.column_stack(
            [
                np.interp(
                    wavelengths,
                    calibration["references"][name]["wl"],
                    calibration["references"][name]["abs"],
                )
                for name in names
            ]
        )

        design = np.column_stack([reference_matrix, np.ones(len(wavelengths))])
        lower_bounds = np.array([0.0] * len(names) + [-np.inf])
        upper_bounds = np.array([np.inf] * (len(names) + 1))
        solution = lsq_linear(design, mixture, bounds=(lower_bounds, upper_bounds))
        coefficients = solution.x[: len(names)]

        fitted = reference_matrix @ coefficients
        residual = mixture - fitted

        ss_res = float(np.sum(residual**2))
        ss_tot = float(np.sum((mixture - np.mean(mixture)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

        mixture_norm = float(np.linalg.norm(mixture))
        relative_error = (
            float(np.linalg.norm(residual)) / mixture_norm if mixture_norm > 0 else 0.0
        )

        concentrations = {}
        for i, name in enumerate(names):
            reference = calibration["references"][name]
            cal_coeffs = reference["cal_coeffs"]
            cal_concs = reference["cal_concs"]
            if len(cal_coeffs) >= 2 and np.std(cal_coeffs) > 0:
                concentrations[name] = float(
                    np.interp(coefficients[i], cal_coeffs, cal_concs)
                )
            else:
                concentrations[name] = float(
                    coefficients[i] * reference["ref_conc"]
                )

        self.log(
            f"Unmixing results: R2={r2:.4f}, relative residual={relative_error:.4f}"
        )
        for name, concentration in concentrations.items():
            self.log(
                f"  {name}: {concentration:.6e} M "
                f"({concentration * 1000.0:.6f} {_CONCENTRATION_UNITS})"
            )

        return {
            "concentrations": concentrations,
            "r2": r2,
            "relative_error": relative_error,
            "contributions": {
                name: coefficients[i] * reference_matrix[:, i]
                for i, name in enumerate(names)
            },
        }

    def _process_analytics(
        self,
        data: pd.DataFrame,
        recipe: list[RecipeComponent],
        non_spectrometer_parameters: dict,
        conditions: dict,
    ) -> dict:
        """
        Process the spectral data.

        Primary path: spectral unmixing against the calibration file
        ('path_to_calibration_file'), giving the concentration of each calibrated
        component. Fallback: Beer-Lambert single-point/integrated absorbance.
        """
        self.log("Processing UV data", indent="enter")

        if data is None or data.empty:
            self.log("No data to process", level="warning", indent="exit")
            return {
                "PI_conc": None,
                "SM_conc": None,
                "PI_area": 0,
                "SM_area": 0,
                "SM_var": 0,
                "PI_var": 0,
            }

        metrics: dict[str, Any] = {}

        # integration bounds (used for the integral metrics)
        integration_parameters = non_spectrometer_parameters.get(
            "simple_integration", {}
        )
        lb = integration_parameters.get("integration_lower_bound", None)
        ub = integration_parameters.get("integration_upper_bound", None)
        lb_value = getattr(lb, "value", 200) if lb is not None else 200
        ub_value = getattr(ub, "value", 600) if ub is not None else 600

        # ---- primary path: spectral unmixing ----
        calibration_path = non_spectrometer_parameters.get("all", {}).get(
            "path_to_calibration_file"
        )
        calibration = None
        if calibration_path is not None:
            calibration = self._load_calibration(calibration_path.value)

        if calibration is not None:
            product_chemical = non_spectrometer_parameters.get("all", {}).get(
                "product_chemical"
            )
            product_name = (
                product_chemical.value if product_chemical is not None else ""
            )
            yield_chemical = conditions.get("yield_calculation_chemical")
            yield_chemical_name = (
                yield_chemical.value if yield_chemical is not None else ""
            )

            unmix = self._unmix_spectrum(data, calibration)
            concentrations_mM = {
                name: value * 1000.0
                for name, value in unmix["concentrations"].items()
            }

            product_name = product_name if product_name in concentrations_mM else ""
            if product_chemical is not None and product_chemical.value and not product_name:
                self.log(
                    f"Product chemical '{product_chemical.value}' not found in "
                    f"calibration components {list(concentrations_mM.keys())}.",
                    level="warning",
                )

            wavelengths = data.iloc[:, 0].to_numpy(dtype=float)
            if product_name:
                metrics["PI_conc"] = concentrations_mM[product_name]
                product_contribution = unmix["contributions"][product_name]
                mask = (wavelengths >= lb_value) & (wavelengths <= ub_value)
                metrics["PI_area"] = (
                    float(np.trapz(product_contribution[mask], wavelengths[mask]))
                    if mask.any()
                    else 0.0
                )
            else:
                metrics["PI_conc"] = None
                metrics["PI_area"] = 0.0

            if yield_chemical_name in concentrations_mM:
                metrics["SM_conc"] = concentrations_mM[yield_chemical_name]
                sm_contribution = unmix["contributions"][yield_chemical_name]
                mask = (wavelengths >= lb_value) & (wavelengths <= ub_value)
                metrics["SM_area"] = (
                    float(np.trapz(sm_contribution[mask], wavelengths[mask]))
                    if mask.any()
                    else 0.0
                )
            else:
                metrics["SM_conc"] = None
                metrics["SM_area"] = 0.0

            relative_error = unmix["relative_error"]
            metrics["PI_var"] = (
                (metrics["PI_conc"] * relative_error) ** 2
                if metrics["PI_conc"] is not None
                else 0.0
            )
            metrics["SM_var"] = (
                (metrics["SM_conc"] * relative_error) ** 2
                if metrics["SM_conc"] is not None
                else 0.0
            )
            metrics["unmixed_concentrations"] = concentrations_mM
            metrics["unmix_r2"] = unmix["r2"]
            metrics["absorbance_at_wlen"] = float(
                data.iloc[:, 1].to_numpy(dtype=float).max()
            )

            self.log("Data processed successfully (spectral unmixing)", indent="exit")
            return metrics

        # ---- fallback path: Beer-Lambert ----
        self.log(
            "No valid calibration file, falling back to Beer-Lambert processing.",
            level="warning",
        )
        wavelengths = data.iloc[:, 0].to_numpy(dtype=float)
        absorbances = data.iloc[:, 1].to_numpy(dtype=float)

        mask = (wavelengths >= lb_value) & (wavelengths <= ub_value)
        if mask.any():
            integrated_absorbance = float(np.trapz(absorbances[mask], wavelengths[mask]))
            max_absorbance = float(np.max(absorbances[mask]))
        else:
            integrated_absorbance = 0.0
            max_absorbance = 0.0

        metrics["PI_area"] = integrated_absorbance
        metrics["SM_area"] = 0.0

        epsilon = (
            non_spectrometer_parameters.get("all", {}).get(
                "molar_extinction_coefficient", 1.0
            )
        )
        epsilon_value = (
            getattr(epsilon, "value", 1.0) if hasattr(epsilon, "value") else 1.0
        )

        if epsilon_value > 0:
            pi_conc = max_absorbance / epsilon_value
        else:
            pi_conc = max_absorbance

        metrics["PI_conc"] = pi_conc
        metrics["SM_conc"] = pi_conc * 0.0  # No SM tracking in basic UV
        metrics["PI_var"] = 0.01
        metrics["SM_var"] = 0.01
        metrics["absorbance_at_wlen"] = max_absorbance

        self.log("Data processed successfully (Beer-Lambert)", indent="exit")
        return metrics

    def _make_results(
        self,
        metrics: dict,
        recipe: list,
        conditions: dict,
    ) -> dict:
        """
        Build the results dictionary from metrics.

        Yield calculation:
            yield = (c_product * dilution_factor) /
                    (c_controlled * (nu_product / nu_reactant))
        where c_product is the unmixed product concentration (mM),
        dilution_factor is the frontend-configured dilution of the sample,
        nu_product / nu_reactant are the stoichiometric coefficients of the reaction
        equation and c_controlled is the concentration of the controlled (limiting)
        reactant from the recipe (mM).
        """
        self.log("Making results", indent="enter")

        results = {}

        pi_conc = metrics.get("PI_conc", None)
        sm_conc = metrics.get("SM_conc", None)
        pi_area = metrics.get("PI_area", 0)
        sm_area = metrics.get("SM_area", 0)
        sm_var = metrics.get("SM_var", 0)
        pi_var = metrics.get("PI_var", 0)

        if pi_conc is None:
            self.log("Concentrations missing, setting yield to None.", level="warning")
            results.update(
                {
                    "yield": None,
                    "yield_variance": None,
                    "integral": pi_area,
                    "integral_starting_material": sm_area,
                    "absorbance_at_wlen": metrics.get("absorbance_at_wlen", pi_area),
                    "concentration_product": pi_conc,
                    "unmixed_concentrations": metrics.get(
                        "unmixed_concentrations", {}
                    ),
                    "unmix_r2": metrics.get("unmix_r2", None),
                    "pass": True,
                }
            )
            return results

        try:
            yield_calculation_chemical = conditions.get(
                "yield_calculation_chemical", None
            )
            if (
                yield_calculation_chemical is not None
                and yield_calculation_chemical.value
            ):
                reference_concentration = self.get_reference_concentration(
                    yield_calculation_chemical.value, recipe
                )
                self.log(f"Reference concentration: {reference_concentration} mM")
            else:
                reference_concentration = None
        except Exception as e:
            self.log(f"Error getting reference concentration: {e}", level="error")
            results["pass"] = False
            return results

        # frontend-configured factors
        dilution_factor = self._condition_value(conditions, "dilution_factor", 1.0)
        nu_product = self._condition_value(
            conditions, "stoichiometry_product_coefficient", 1.0
        )
        nu_reactant = self._condition_value(
            conditions, "stoichiometry_reactant_coefficient", 1.0
        )
        stoichiometric_ratio = (
            nu_product / nu_reactant if nu_reactant else float("inf")
        )

        product_concentration = pi_conc * dilution_factor
        yield_variance = pi_var * (dilution_factor**2)
        conversion_value = None

        if reference_concentration is not None and reference_concentration > 0:
            yield_value = product_concentration / (
                reference_concentration * stoichiometric_ratio
            )
            self.log(
                f"Yield calculation: c_product={pi_conc:.6e} mM x dilution="
                f"{dilution_factor} / (c_reference={reference_concentration:.6e} mM "
                f"x stoichiometry={nu_product}/{nu_reactant}) = {yield_value}"
            )
        else:
            yield_value = product_concentration
            self.log(
                "No valid reference concentration, yield reported as diluted "
                "product concentration.",
                level="warning",
            )

        results.update(
            {
                "yield": yield_value,
                "yield_variance": yield_variance,
                "conversion": conversion_value,
                "integral": pi_area,
                "integral_starting_material": sm_area,
                "absorbance_at_wlen": metrics.get("absorbance_at_wlen", pi_area),
                "concentration_product": product_concentration,
                "concentration_product_variance": pi_var,
                "concentration_starting_material": sm_conc,
                "concentration_starting_material_variance": sm_var,
                "unmixed_concentrations": metrics.get("unmixed_concentrations", {}),
                "unmix_r2": metrics.get("unmix_r2", None),
                "dilution_factor": dilution_factor,
            }
        )

        if metrics.get("unmix_r2") is not None:
            # Spectral unmixing path: quality is judged by the fit quality.
            # The unmixed product contribution may integrate to a negative
            # value (solvent displacement), which is not a failure.
            pass_criteria = {
                "yield_valid": yield_value is not None and yield_value >= 0,
                "unmix_fit_good": metrics["unmix_r2"] >= 0.9,
            }
        else:
            pass_criteria = {
                "yield_valid": yield_value is not None and yield_value >= 0,
                "area_positive": pi_area > 0,
            }
        results["pass"] = all(pass_criteria.values())

        self.log(
            f"Pass status: {'PASS' if results['pass'] else 'FAIL'}",
            level="ok" if results["pass"] else "warning",
        )
        self.log("Results generated", indent="exit")
        return results

    @staticmethod
    def _condition_value(conditions: dict, name: str, default: Any) -> Any:
        """Read a value from the conditions dict, with a fallback default."""
        parameter = conditions.get(name, None)
        if parameter is None:
            return default
        return parameter.value if hasattr(parameter, "value") else parameter
