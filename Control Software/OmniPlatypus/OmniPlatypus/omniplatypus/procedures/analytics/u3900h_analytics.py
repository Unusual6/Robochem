"""
Author: Robochem U3900H Integration

Descr: Analytics class for Hitachi U-3900H UV-Vis Spectrometer.
       Handles scan acquisition, absorbance processing, and concentration/yield calculation.
"""

import os.path
from typing import Any

import numpy as np
import pandas as pd

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
from omniplatypus.utilities.general import (
    get_function_from_globals,
)


class AnalyticsU3900H(AnalyticsTemplate):
    """
    UV-Vis Analysis class for Hitachi U-3900H spectrometer.

    Supports wavelength scanning and absorbance-based concentration analysis.
    Processing methods: single_point_absorbance, integrated_absorbance
    """

    _base_data = os.path.join("uv_spectra")
    result_metrics: list[str] = [
        "yield",
        "integral",
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
            value=250,
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
        AnalyticalParameter(name="path_to_calibration_file", tag="all", value=""),
    ]

    _processing_methods = ["single_point_absorbance", "integrated_absorbance"]

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
            Chemical conditions, reagents and their concentrations.
        @param process_only: bool = False
            If true, skip acquisition and process existing data.
        @return: dict
            Results dictionary with yield, integral, absorbance, pass/fail.
        """
        self.log(f"[DIAG] analyse() called, process_only={process_only}, device={self._device}")

        _parameters = self.validate_parameters(conditions)
        non_spectrometer_parameters = self._split_parameters(_parameters)

        if not process_only:
            self.log(f"[DIAG] Calling _set_parameters()")
            self._set_parameters(conditions)
            self.log(f"[DIAG] Calling _spectrometer_run()")
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
            what_to_copy = str(
                os.path.join(
                    conditions["data_folder"].value,
                    conditions["sample_name"].value + ".csv",
                )
            )
            self.save_files(path=what_to_copy)

        return results

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

        self.log(f"[DIAG] _device is_open={self._device.is_open()}, initialized={self._device.is_initialized()}")

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
        """Read data from a CSV file. Stub implementation."""
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

    def _process_analytics(
        self,
        data: pd.DataFrame,
        recipe: list[RecipeComponent],
        non_spectrometer_parameters: dict,
        conditions: dict,
    ) -> dict:
        """
        Process spectral data to extract absorbance and concentration metrics.

        For now, implements simple absorbance-at-wavelength and integration methods.
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

        metrics = {}

        wl_col = data.columns[0] if len(data.columns) > 0 else "wavelength"
        ab_col = data.columns[1] if len(data.columns) > 1 else "absorbance"

        wavelengths = data[wl_col].values
        absorbances = data[ab_col].values

        # Get integration bounds if available
        integration_params = non_spectrometer_parameters.get(
            "simple_integration", {}
        )
        lb = integration_params.get("integration_lower_bound", None)
        ub = integration_params.get("integration_upper_bound", None)

        if lb is not None and ub is not None:
            lb_val = getattr(lb, "value", 200)
            ub_val = getattr(ub, "value", 1100)

            # Integration within bounds
            mask = (wavelengths >= lb_val) & (wavelengths <= ub_val)
            if mask.any():
                integrated_absorbance = np.trapz(
                    absorbances[mask], wavelengths[mask]
                )
                max_absorbance = float(np.max(absorbances[mask]))
            else:
                integrated_absorbance = 0.0
                max_absorbance = 0.0

            metrics["PI_area"] = integrated_absorbance
            metrics["SM_area"] = 0.0
        else:
            max_absorbance = float(np.max(absorbances)) if len(absorbances) > 0 else 0.0
            metrics["PI_area"] = max_absorbance
            metrics["SM_area"] = 0.0

        # Simple Beer-Lambert: A = epsilon * c * l
        epsilon = (
            non_spectrometer_parameters.get("all", {})
            .get("molar_extinction_coefficient", 1.0)
        )
        epsilon_val = getattr(epsilon, "value", 1.0) if hasattr(epsilon, "value") else 1.0

        if epsilon_val > 0:
            pi_conc = max_absorbance / epsilon_val
        else:
            pi_conc = max_absorbance

        metrics["PI_conc"] = pi_conc
        metrics["SM_conc"] = pi_conc * 0.0  # No SM tracking in basic UV
        metrics["PI_var"] = 0.01
        metrics["SM_var"] = 0.01

        self.log("Data processed successfully", indent="exit")
        return metrics

    def _make_results(
        self,
        metrics: dict,
        recipe: list,
        conditions: dict,
    ) -> dict:
        """Build results dictionary from metrics."""
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
                    "absorbance_at_wlen": pi_area,
                    "concentration_product": pi_conc,
                    "pass": True,
                }
            )
            return results

        try:
            yield_calculation_chemical = conditions.get(
                "yield_calculation_chemical", None
            )
            if yield_calculation_chemical is not None:
                reference_concentration = self.get_reference_concentration(
                    yield_calculation_chemical.value, recipe
                )
                self.log(
                    f"Reference concentration: {reference_concentration}"
                )
            else:
                reference_concentration = 1.0
        except Exception as e:
            self.log(f"Error getting reference concentration: {e}", level="error")
            results["pass"] = False
            return results

        yield_value = pi_conc if pi_conc is not None else None
        yield_variance = 0.01
        conversion_value = None

        results.update(
            {
                "yield": yield_value,
                "yield_variance": yield_variance,
                "conversion": conversion_value,
                "integral": pi_area,
                "integral_starting_material": sm_area,
                "absorbance_at_wlen": pi_area,
                "concentration_product": pi_conc,
            }
        )

        pass_criteria = {
            "yield_valid": yield_value is not None,
            "area_positive": pi_area > 0,
        }
        results["pass"] = all(pass_criteria.values())

        self.log(
            f"Pass status: {'PASS' if results['pass'] else 'FAIL'}",
            level="ok" if results["pass"] else "warning",
        )
        self.log("Results generated", indent="exit")
        return results