"""
File: photochemistry.py
Author: Simone Pilon - Noël Research Group - 2024
GitHub: https://github.com/simone16

Description: Photochemical experiments procedures.
"""

import time
import os
import random
from threading import Thread, Event
from typing import Any

import pandas as pd

from omniplatypus.devices.base.device import DeviceParameter
from omniplatypus.devices.magritek.spinsolve import SpinsolveClient
from omniplatypus.devices.nrg.rama_berry import RamaBerry
from omniplatypus.devices.nrg.sampler import DummySampler
from omniplatypus.devices.nrg.light import LightSource
from omniplatypus.procedures.analytics.analytics_parameters import AnalyticalParameter
from omniplatypus.procedures.analytics.nmr_analysis import DummyNMRAnalysis
from omniplatypus.procedures.analytics.hplc_analysis import dummyHPLCAnalysis
from omniplatypus.procedures.analytics.raman_analysis import (
    AnalyticsRaman,
)
from omniplatypus.procedures.analytics.u3900h_analytics import AnalyticsU3900H
from omniplatypus.procedures.experiments.chemistry import ChemicalReaction
from omniplatypus.procedures.experiments.experiment_parameters import (
    ExperimentalParameter,
    NumericalParameter,
    RunResult,
)
from omniplatypus.utilities.general import dict_to_str
from omniplatypus.procedures.experiments.base_experiment import (
    ExperimentAnalysisCoupler,
    BaseExperiment,
)
from omniplatypus.procedures.unit_tasks.sampling.liquid_handler_sampling import (
    RecipeComponent,
    GenerateComposition,
    FindVial,
    OrderRecipe,
)
from omniplatypus.procedures.unit_tasks.reactor.light import SetLightSourceIntensity
from omniplatypus.procedures.unit_tasks.sensing.monitoring import (
    ContinuousMonitoring,
    MonitoredValue,
)


class PhotochemicalReaction(ChemicalReaction):
    """
    Basic procedure for photochemical reaction experiments on platform Perry.
    In addition to the base ChemicalReaction requirements, this experiment sets light intensity via a light control
    device.
    """

    _required_parameters: list[ExperimentalParameter] = [
        NumericalParameter(
            "light_intensity", 100.0, "%", min_value=0.0, max_value=100.0
        ),
    ] + ChemicalReaction.get_required_parameters()

    _required_devices: set[str] = ChemicalReaction._required_devices.union(
        {
            "Light_Array",
        }
    )

    _light: LightSource
    _stop_monitoring: Event
    _monitoring_thread: Thread | None

    def __init__(
        self,
        analytical_method: str | None = None,
    ) -> None:
        """
        Constructor.

        @param analytical_method: str | None = None
            The analytical method to build the platform with.
            Must match exactly one of the keys of cls._analytical_methods (or None).
        """
        super().__init__(analytical_method=analytical_method)

        self._stop_monitoring = Event()
        self._monitoring_thread = None

    # noinspection PyTypeChecker
    def _procedure_build(self) -> None:
        ChemicalReaction._procedure_build(self)
        self._light = self._platform["uflow_kessil"]

        # We keep checking the current consumed by the light array device.
        # At the moment nothing about this is checked, but the readings are logged.
        light_monitoring = MonitoredValue(
            device=self._platform["Light_Array"],
            parameter_name="current",
            checks=None,
            store_values=4,
        )
        self._stop_monitoring.clear()
        self._monitoring_thread = ContinuousMonitoring.get_thread(
            values_to_monitor=[light_monitoring],
            stop_event=self._stop_monitoring,
            update_delay=30.0,
        )
        self._monitoring_thread.start()

    def _reactor_prepare(
        self, conditions: dict[str, ExperimentalParameter | NumericalParameter]
    ) -> None:
        """
        Prepare the reactor for the reaction. This is called before the start of the run, to allow maximum time for
        the reactor to be ready.
        Sets the light intensity of the reactor.

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        """
        light_intensity = conditions["light_intensity"].set_units("%", 0)
        light_intensity = int(round(light_intensity / 25.0, 0) * 25.0)
        conditions["light_intensity"].value = light_intensity
        SetLightSourceIntensity.run(source=self._light, intensity=light_intensity)

    def _reactor_wait_until_ready(
        self,
        conditions: dict[str, ExperimentalParameter | NumericalParameter],
    ) -> None:
        """
        This is called before starting the reaction and pumping the slug in the reactor.
        It should only return once the reactor parameters are stable and at the desired levels.

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        """
        pass

    def _reactor_standby(
        self, conditions: dict[str, ExperimentalParameter | NumericalParameter]
    ) -> None:
        """
        Set the reactor in the standby configuration. This is called after the slug has exited the reactor.
        Turns off the light source.

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        """
        SetLightSourceIntensity.run(source=self._light, intensity=0)

    def _procedure_shutdown(self) -> None:
        """
        Shut down procedure of the experimental platform, ensuring all devices are properly
        turned off or reset.
        """
        self._stop_monitoring.set()
        if self._monitoring_thread is not None:
            self._monitoring_thread.join(timeout=300)
        ChemicalReaction._procedure_shutdown(self)


class PhotochemicalReactionDryRun(PhotochemicalReaction):
    """
    Simulate a Photochemical reaction without connecting to any hardware.
    This is for debugging purposes only.
    """

    _required_devices: set[str] = {
        "Sampler_cnc",
        "Collector_cnc",
    }  # Names of required devices (see platform_config.json)

    _analytical_methods: dict[str, ExperimentAnalysisCoupler] = {
        "Human": ExperimentAnalysisCoupler(
            analysis_class=None,
            analytical_device=None,
            platform_constants_key="Human",
        ),
        "UV": ExperimentAnalysisCoupler(
            analysis_class=AnalyticsU3900H,
            analytical_device="UV_Spectrometer",
            platform_constants_key="UV",
        ),
    }  # Analytical methods supported by the experiment

    # noinspection PyTypeChecker
    def _procedure_build(self) -> None:
        self._platform.user_action_requester = self._wait_for_user_action

        # Force platform to use Dummy device instead of real sampler.
        self._platform.device_constructors["liquid_handler_sampler"] = DummySampler
        # Replace known devices finder with dictionary with fake data to trick platform into connecting without device.
        self._platform._known_devices = {"LH_cnc": "COM1", "FC_cnc": "COM2"}
        BaseExperiment._procedure_build(self)
        self._sampler = self._platform["Sampler_cnc"]
        self._collector = self._platform["Collector_cnc"]

    def _procedure_prepare(self) -> None:
        pass

    def _procedure_experiment(
        self,
        results: RunResult,
        conditions: dict[
            str, ExperimentalParameter | NumericalParameter | AnalyticalParameter
        ],
        recipe: list[RecipeComponent],
    ) -> None:
        """
        This method runs the experimental procedure, it must be implemented in the subclasses.
        Note that cleanup procedure should be implemented separately (see self._procedure_cleanup).
        This method must be implemented by non-dummy experiments.

        @param results: RunResult
            Any information acquired during the experiment and which needs to be accessed later, such as yield, spectra
            or other, should be stored here. Once the experiment is complete this object is returned.
        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run are given here.
        @param recipe: list[RecipeComponent]
            Chemical conditions, reagents and their concentrations, are given here.
        """
        run_id = results.run_id
        self._log(f"Run [{run_id}]: Setting up parameters...")

        # evaluate conditions and set rounding according to precision
        slug_volume = conditions["slug_volume"].set_units("uL", 1)
        conditions["residence_time"].set_units("S", 1)
        conditions["light_intensity"].set_units("%", 0)
        direct_slug_preparation = conditions["sampling"].value == "direct"
        sampler_recipe, recipe = GenerateComposition.run(
            platform=self._platform,
            experiment_recipe=recipe,
            slug_volume=slug_volume if direct_slug_preparation else slug_volume + 200.0,
            sampler_name="Sampler_cnc",
        )
        OrderRecipe.run(
            recipe=sampler_recipe, method=conditions["slug_preparation"].value
        )

        light_intensity = conditions["light_intensity"].set_units("%", 0)
        light_intensity = int(round(light_intensity / 25.0, 0) * 25.0)
        conditions["light_intensity"].value = light_intensity

        collect = conditions["collect_crude"].value
        collection_vial_id = conditions["collection_vial"].value
        if collect and collection_vial_id == "":
            # find a suitable vial.
            collection_vial_id = FindVial.run(
                platform=self._platform,
                sampler=self._collector,
                vial_type="Sample",
                nominal_volume=1500.0,  # we need a gc vial
                ensure_volume=slug_volume,
            )
            if collection_vial_id is None:
                collection_vial_id = ""

        self._platform.samples.loc[collection_vial_id, ("Volume", "Viable")] = [
            slug_volume,
            False,
        ]
        time.sleep(0.1)
        results.collection_vial_id = collection_vial_id

        # Call the analytical method to generate analysis results (e.g. yield)
        if self._analytical_method is not None:
            self._log(f"Run [{run_id}]: Dry-run analysis started...")
            results.result = self._analytical_method.analyse(
                conditions=conditions,
                recipe=recipe,
            )
            self._log(
                f"Run [{run_id}]: Dry-run analysis finished:\n{dict_to_str(results.result)}",
                level="ok",
            )

        results.success = True

    def _procedure_cleanup(self) -> None:
        pass

    def _procedure_shutdown(self) -> None:
        """
        Shut down procedure of the experimental platform, ensuring all devices are properly
        turned off or reset.
        """
        ChemicalReaction._procedure_shutdown(self)
