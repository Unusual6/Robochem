"""
File: chemistry.py
Author: Simone Pilon - Noël Research Group - 2024
GitHub: https://github.com/simone16

Description: Generic chemical experiments procedures.
"""

import pandas as pd
from threading import Thread, Event
import time

from omniplatypus.devices.errors import DeviceTimeoutError
from omniplatypus.utilities.general import (
    ThreadEx,
    run_all,
    time_of_completion,
    dict_to_str,
    format_float,
)
from omniplatypus.devices.nrg.syringe_pump import SyringePump
from omniplatypus.devices.nrg.sampler import Sampler
from omniplatypus.devices.nrg.gpio import SolenoidValve
from omniplatypus.devices.nrg.phase_sensor import PhaseSensor
from omniplatypus.procedures.analytics.hplc_analysis import HPLCAnalysis
from omniplatypus.procedures.analytics.nmr_analysis import NMRAnalysis, DummyNMRAnalysis

from omniplatypus.procedures.experiments.experiment_parameters import (
    ExperimentalParameter,
    NumericalParameter,
    RunResult,
)
from omniplatypus.procedures.experiments.base_experiment import (
    ExperimentAnalysisCoupler,
    BaseExperiment,
)
from omniplatypus.procedures.analytics.raman_analysis import AnalyticsRaman
from omniplatypus.procedures.analytics.u3900h_analytics import AnalyticsU3900H
from omniplatypus.procedures.unit_tasks.driving.driving_pumps import (
    FillPump,
    PrimePump,
    PumpVolume,
    MixSlug,
)
from omniplatypus.procedures.unit_tasks.sampling.liquid_handler_moving import (
    HomeSampler,
)
from omniplatypus.procedures.unit_tasks.sampling.liquid_handler_sampling import (
    GenerateSampleDataframe,
    RecipeComponent,
    GenerateComposition,
    FindVial,
    OrderRecipe,
    PumpSample,
    CleanNeedle,
    PrepareReactionSlug,
    MixSlugSampler,
    NoSuitableVialError,
    GetVialInfo,
)
from omniplatypus.procedures.unit_tasks.sampling.liquid_handler_injecting import (
    Inject,
    ConnectInjectionPort,
)
from omniplatypus.procedures.unit_tasks.sensing.phase_sensors import (
    PumpUntilPhaseChange,
    SlugQualityCheck,
    MonitorPhase,
)
from omniplatypus.procedures.unit_tasks.errors import BadSlugQualityError, CloggingError


class ChemicalReaction(BaseExperiment):
    """
    Basic procedure for chemical reaction experiments on platform Perry.
    This is suitable for reactors with no automated parameters, but can be expanded to control specific reactors.

    Uses 2 syringe pumps and 2 samplers:
        - One syringe pump + sampler to create the slug
        - One larger syringe pump to push the slug through the system
        - One sampler which collects the slug after the reaction
        - Solenoid valve control, phase sensors.

    In-line analytics are inserted between the reactor and the collector, when available.

    Note on back pressure:
    Slug injection should be performed with minimal backpressure.
    Case 1: Analytics with high back pressure (default)
        In the platform config, set the sampling constant 'redirect_reactor_to_waste' to true, to avoid analytics
        backpressure during injection.
    Case 2: Reaction with BPR
        In this case mount the BPR after the reactor 3-way valve on the waste side and set the redirect_reactor_to_waste
        to false during sampling (injection), but to true during the reaction (in the reaction section of the constants).
        This setup requires an additional volume between reactor and valve to park the slug. Set the volume of this
        loop in the reaction constants.
    """

    _analytical_methods: dict[str, ExperimentAnalysisCoupler] = {
        "Human": ExperimentAnalysisCoupler(
            analysis_class=None,
            analytical_device=None,
            platform_constants_key="Human",
        ),
        "NMR_dummy": ExperimentAnalysisCoupler(
            analysis_class=DummyNMRAnalysis,
            analytical_device="NMR",
            platform_constants_key="NMR_dummy",
        ),
        "NMR": ExperimentAnalysisCoupler(
            analysis_class=NMRAnalysis,
            analytical_device="NMR",
            platform_constants_key="NMR",
        ),
        "UPLC": ExperimentAnalysisCoupler(
            analysis_class=HPLCAnalysis,
            analytical_device="UPLC",
            platform_constants_key="UPLC",
        ),
        "Raman": ExperimentAnalysisCoupler(
            analysis_class=AnalyticsRaman,
            analytical_device="Raman",
            platform_constants_key="Raman",
        ),
        "UV": ExperimentAnalysisCoupler(
            analysis_class=AnalyticsU3900H,
            analytical_device="UV_Spectrometer",
            platform_constants_key="UV",
        ),
    }  # Analytical methods supported by the experiment

    _required_parameters: list[ExperimentalParameter] = [
        NumericalParameter(
            "residence_time", 60.0, "S", min_value=30.0, max_value=100000.0
        ),
    ]  # These parameters must be included for each run
    _optional_parameters: list[ExperimentalParameter] = [
        NumericalParameter(
            "slug_volume", 500.0, "uL", min_value=100.0, max_value=1000.0
        ),
        NumericalParameter("rinse", 1.0, "bool"),
        NumericalParameter("gas_purging_cycles", 3, "int", min_value=0, max_value=20),
        NumericalParameter(
            "gas_purging_amplitude",
            100.0,
            "uL",
            min_value=10.0,
            max_value=500.0,
        ),
        NumericalParameter(
            "gas_purging_flowrate", 2.0, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "mix_before_injection_cycles", 6, "int", min_value=0, max_value=20
        ),
        NumericalParameter(
            "mix_before_injection_amplitude",
            200.0,
            "uL",
            min_value=10.0,
            max_value=500.0,
        ),
        NumericalParameter(
            "mix_before_injection_flowrate",
            2.0,
            "mL/min",
            min_value=0.1,
            max_value=5.0,
        ),
        NumericalParameter(
            "mix_after_injection_cycles", 0, "int", min_value=0, max_value=20
        ),
        NumericalParameter(
            "mix_after_injection_amplitude",
            300.0,
            "uL",
            min_value=10.0,
            max_value=500.0,
        ),
        NumericalParameter(
            "mix_after_injection_flowrate",
            2.0,
            "mL/min",
            min_value=0.1,
            max_value=5.0,
        ),
        ExperimentalParameter("collect_crude", True),
        ExperimentalParameter("collection_vial", ""),  # if empty finds a suitable vial
        NumericalParameter(
            "flowrate_gas_sampling", 0.5, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_sampling", 0.5, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_injection", 1.0, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_slug_check", 1.0, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_slug_verification", 1.0, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_delivery", 2.0, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_analysis_loading", 2.0, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter(
            "flowrate_collection", 0.5, "mL/min", min_value=0.1, max_value=10.0
        ),
        NumericalParameter("bubble_volume", 50.0, "uL", min_value=0.0, max_value=200.0),
        NumericalParameter(
            "intercomponent_bubble_volume", 0.2, "uL", min_value=0.0, max_value=50.0
        ),
        ExperimentalParameter(
            "slug_preparation", "middle", allowed_values=OrderRecipe.sorting_methods()
        ),
        NumericalParameter(
            "slug_check_volume", 1100.0, "uL", min_value=10.0, max_value=8000.0
        ),
        NumericalParameter(
            "slug_check_max_deviation", 5.0, "%", min_value=0.1, max_value=100.0
        ),
        ExperimentalParameter("sampling", "direct", allowed_values=["direct", "vial"]),
        NumericalParameter(
            "collection_vial_volume", 1500.0, "uL", min_value=1500.0, max_value=10000.0
        ),
        NumericalParameter(
            "reactor_volume", 3900.0, "uL", min_value=2000.0, max_value=8000.0
        ),
        NumericalParameter(
            "delay_collection", 2.0, "S", min_value=0.0, max_value=120.0
        ),
        NumericalParameter("delay_injection", 5.0, "S", min_value=0.0, max_value=120.0),
        NumericalParameter(
            "reactor_timeout", 300.0, "S", min_value=0.0, max_value=3600.0
        ),
        NumericalParameter(
            "slug_verification_volume", 100.0, "uL", min_value=0.0, max_value=8000.0
        ),
        NumericalParameter(
            "slug_verification_threshold", 80.0, "%", min_value=0.1, max_value=100.0
        ),
        # Note: the following are for feedback purposes, the values set here do not affect the experiment.
        NumericalParameter(
            "measured_residence_time",
            0.0,
            "S",
            min_value=0.0,
            max_value=100000.0,
        ),
        NumericalParameter(
            "measured_slug_volume", 0.0, "uL", min_value=0.0, max_value=10000.0
        ),
    ]  # These parameters take the default value if unspecified

    _required_devices: set[str] = {
        "Main_Pump_1",
        "Sampler_cnc",
        "Sampler_pump",
        "Collector_cnc",
        "Gpio_Array_1",
        "Phase_Sensor_Array_1",
        "Phase_Sensor_Array_2",
    }  # Names of required devices (see platform_config.json)

    _main_pump: SyringePump
    _sampler: Sampler
    _collector: Sampler
    _sampler_pump: SyringePump
    _n2_valve: SolenoidValve
    _ps_sampler: PhaseSensor
    _ps_reactor_in: PhaseSensor
    _ps_reactor_out: PhaseSensor
    _ps_out: PhaseSensor
    _input_samples: pd.DataFrame

    _analysis_coupling: ExperimentAnalysisCoupler

    _reactor_monitoring_stop_event: Event | None
    _reactor_monitoring_thread: Thread | None
    _reactor_monitoring_data: dict | None
    _reactor_monitoring_delta_t: float

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
        self._circuit_is_clean = False  # If true cleaning is skipped
        self._discard_slug = False  # If true only the slug chamber is cleaned
        self._reactor_monitoring_stop_event = None
        self._reactor_monitoring_thread = None
        self._measured_residence_time = None
        self._reactor_monitoring_data = None
        self._reactor_monitoring_delta_t = 0.5

    # noinspection PyTypeChecker
    def _procedure_build(self) -> None:
        self._platform.user_action_requester = self._wait_for_user_action
        BaseExperiment._procedure_build(self)
        self._main_pump = self._platform["Main_Pump_1"]
        self._sampler = self._platform["Sampler_cnc"]
        self._collector = self._platform["Collector_cnc"]
        self._sampler_pump = self._platform["Sampler_pump"]
        self._n2_valve = self._platform["sv_injection_n2"]
        self._ps_sampler = self._platform["ps_handler_out"]
        self._ps_reactor_in = self._platform["ps_reactor_in"]
        self._ps_reactor_out = self._platform["ps_reactor_out"]
        self._ps_out = self._platform["ps_out"]

    def _procedure_update_samples(self, samples: pd.DataFrame) -> None:
        """
        Should update the platform dataframe based on a new version of the dataframe provided by the user.

        @param samples: pandas.DataFrame
            An updated version of the samples dataframe.
        """
        GenerateSampleDataframe.run(platform=self._platform, samples=samples)

    def _procedure_prepare(self) -> None:
        ConnectInjectionPort.run(
            platform=self._platform,
            sampler=self._sampler,
            port_name="injection_flow",
            inject=False,
        )
        run_all(
            PrimePump.get_thread(pump=self._main_pump, cycles=1),
            PrimePump.get_thread(pump=self._sampler_pump, cycles=1),
        )
        if self._platform_constants["cleaning"].get("clean_on_start", True):
            self._procedure_cleanup()

    def _redirect_reactor_to_waste(self, to_waste: bool) -> None:
        """
        Set the switchvalve after the reactor to either send connect to the waste or to the analysis and collection.
        This is to avoid overpressure in the system, if caused by the analysis.

        @param to_waste: bool
            If True, the connection is made with the waste, otherwise the switchvalve will connect to the analysis and
            collection.
        """
        setpoint = "OFF" if to_waste else "ON"
        self._main_pump["aux_valve_setpoint"] = setpoint

    def _reactor_prepare(
        self, conditions: dict[str, ExperimentalParameter | NumericalParameter]
    ) -> None:
        """
        Prepare the reactor for the reaction. This is called before the start of the run, to allow maximum time for
        the reactor to be ready (e.g.: set temperature, light, or other reactor parameter).

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        """
        pass

    def _reactor_wait_until_slug_can_be_prepared(
        self,
        conditions: dict[str, ExperimentalParameter | NumericalParameter],
    ) -> None:
        """
        This is called before starting the reaction and pumping the slug in the reactor.
        It should only return once the reactor parameters are such that we can expect the reactor to be ready after the
        slug has been prepared (5-10min). This prevents the prepared slug from sitting too long waiting for the reactor
        to be ready (avoiding prolonged background reactivity).

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        """
        pass

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

        @param conditions: dict[str, ExperimentalParameter]
            Physical conditions for the run.
        """
        pass

    def _reactor_monitoring_target(self) -> None:
        """
        This is the thread monitoring the reactor.
        """
        phase_data = MonitorPhase.run(
            phase_sensor=self._ps_reactor_out,
            delta_t=self._reactor_monitoring_delta_t,
            stop_event=self._reactor_monitoring_stop_event,
        )
        phase_data["Duration"] = (
            phase_data["Time"]
            .shift(periods=-1, fill_value=phase_data.iloc[-1].at["Time"])
            .sub(phase_data["Time"])
        )
        self._reactor_monitoring_data = {"phase": phase_data}
        self._log(
            f"Reactor monitoring data:\n{dict_to_str(self._reactor_monitoring_data)}"
        )

    def _start_reactor_monitoring(self) -> None:
        """
        Starts the thread which monitors the reactor during a reaction.
        """
        self._reactor_monitoring_stop_event = Event()
        self._reactor_monitoring_thread = Thread(
            target=self._reactor_monitoring_target, name="Reactor Monitoring Thread"
        )
        self._reactor_monitoring_thread.start()

    def _stop_reactor_monitoring(self) -> None:
        """
        Stops the thread which monitors the reactor during a reaction.
        """
        self._reactor_monitoring_stop_event.set()
        self._reactor_monitoring_thread.join(timeout=60.0)

    def _move_slug_and_verify(
        self,
        run_id,
        max_pump_volume,
        phase_sensor,
        flowrate_delivery,
        flowrate_verification,
        volume_verification,
        threshold_verification,
    ) -> bool:
        """
        Delivers the slug and checks a portion of it to make sure it is not a small droplet.

        """
        while max_pump_volume > 0.0:
            pumped_volume = PumpUntilPhaseChange.run(
                pump=self._main_pump,
                phase_sensor=phase_sensor,
                flowrate=flowrate_delivery,
                max_volume=max_pump_volume,
                wait_for_gas=False,
            )
            if pumped_volume is not None:
                max_pump_volume -= pumped_volume
            slug_shape_verification = SlugQualityCheck.run(
                pump=self._main_pump,
                phase_sensor=phase_sensor,
                flowrate=flowrate_verification,
                pump_volume=volume_verification,
            )
            max_pump_volume -= volume_verification
            self._log(
                f"Run [{run_id}]: Partial slug check before analysis:\n{slug_shape_verification}",
                level="ok",
            )
            if (
                slug_shape_verification.liquid_volume
                >= threshold_verification * volume_verification
            ):
                return True
        return False

    def _procedure_experiment(
        self,
        results: RunResult,
        conditions: dict[str, ExperimentalParameter | NumericalParameter],
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
        self._log(f"[{run_id}] Setting up run parameters...")
        # here we try to parse as many parameters as possible to trigger potential errors before any
        # physical operation starts.

        # evaluate conditions and set rounding according to precision
        slug_volume = conditions["slug_volume"].set_units("uL", 1)
        residence_time = conditions["residence_time"].set_units("S", 1)
        collect = conditions["collect_crude"].value
        if not isinstance(collect, bool):
            self._log(
                f"Invalid type for parameter 'collect_crude': {collect}, expected bool."
            )
            collect = True
        collection_vial_id = conditions["collection_vial"].value
        inject_slug = True
        if collect:
            if not collection_vial_id == "":
                # A collection vial was specified
                if collection_vial_id not in self._platform.samples.index:
                    self._log(
                        f"Invalid collection vial id '{collection_vial_id}'.",
                        level="warning",
                    )
                    collection_vial_id = ""
                    conditions["collection_vial"].value = collection_vial_id
                else:
                    # If the specified vial is on the sampler, do not inject slug.
                    sampler_name = self._platform.samples.loc[
                        collection_vial_id, "Sampler"
                    ]
                    inject_slug = not sampler_name == "Sampler_cnc"
                    if sampler_name not in ("Collector_cnc", "Sampler_cnc"):
                        inject_slug = True
                        self._log(
                            f"Collection vial id '{collection_vial_id}' "
                            f"requires a sampler which was not configured '{sampler_name}'.",
                            level="warning",
                        )
                        collection_vial_id = ""
                        conditions["collection_vial"].value = collection_vial_id
            else:
                # find a suitable vial.
                collection_vial_id = FindVial.run(
                    platform=self._platform,
                    sampler=self._collector,
                    vial_type="Sample",
                    nominal_volume=conditions["collection_vial_volume"].with_units(
                        "uL"
                    ),
                    ensure_volume=slug_volume,
                    order_by_distance=False,
                )
                if collection_vial_id is None:
                    collection_vial_id = ""

        # Calculate key reaction parameters
        reactor_volume = conditions["reactor_volume"].set_units("uL", 1)
        reaction_flowrate = 30.0  # in mL/min
        if residence_time >= 5.0:
            reaction_flowrate = (reactor_volume * 1.0e-3) / (residence_time / 60.0)
        self._log(
            f"Calculated reaction flowrate: {format_float(reaction_flowrate)} mL/min"
        )

        mix_cycles_before_injection = int(
            conditions["mix_before_injection_cycles"].value
        )

        slug_tail_bubble_volume = conditions["bubble_volume"].set_units("uL", 1)
        # mixing before the injection adds an extra bubble at the front of the slug.
        slug_head_bubble_volume = (
            slug_tail_bubble_volume if mix_cycles_before_injection > 0 else 0.0
        )
        intercomponent_bubble_volume = conditions[
            "intercomponent_bubble_volume"
        ].set_units("uL", 1)

        reactor_timeout = conditions["reactor_timeout"].set_units("S", 1)

        # Get platform connection volumes and other constants
        try:
            sampling_constants = self._platform_constants["sampling"]
            reaction_constants = self._platform_constants["reaction"]
            analysis_constants = self._platform_constants["analysis"][
                self._analysis_coupling.platform_constants_key
            ]
        except KeyError as error:
            key = error.args[0]
            if key in ("sampling", "analysis", "reaction"):
                error.add_note(
                    f"'{self.__class__.__name__}' experiment requires a '{key}' section"
                    " to be defined within platform_config.json under 'constants'."
                )
            else:
                error.add_note(
                    f"'{self.__class__.__name__}' experiment "
                    f"with analysis '{self._analysis_coupling.analysis_class.__name__}' requires a '{key}'"
                    " sub-section to be defined within platform_config.json under 'constants' > 'analysis'."
                )
            self._log(error)
            raise
        try:
            # all of these volumes are in uL.
            injection_port_volume = sampling_constants["sampler_injection_port_volume"]
            injection_to_mixing_volume = sampling_constants[
                "sampler_injection_to_mixing_volume"
            ]
            # mixing_chamber_volume = 850  # in uL, underestimate
            sampler_to_reactor_max_volume = sampling_constants[
                "sampler_to_reactor_max_volume"
            ]
            reactor_to_collector_max_volume = sampling_constants[
                "reactor_to_collector_max_volume"
            ]
            collector_ps_to_needle_volume = sampling_constants[
                "collector_ps_to_needle_volume"
            ]
            redirect_reactor_to_waste_during_injection = sampling_constants.get(
                "redirect_reactor_to_waste", True
            )
        except KeyError as error:
            key = error.args[0]
            error.add_note(
                f"'{self.__class__.__name__}' experiment requires '{key}'"
                " to be defined within platform_config.json under 'constants' > 'sampling'."
            )
            self._log(error)
            raise
        try:
            analysis_alignment_volume = (
                analysis_constants["slug_alignment_volume"] + slug_volume / 2.0
            )
            analysis_phase_sensor_name = analysis_constants["analysis_phase_sensor"]
            if analysis_phase_sensor_name is not None:
                # noinspection PyTypeChecker
                analysis_phase_sensor: PhaseSensor | None = self._platform[
                    analysis_phase_sensor_name
                ]
            else:
                analysis_phase_sensor = None
            reactor_to_analysis_volume = analysis_constants[
                "reactor_to_analysis_volume"
            ]
            analysis_to_collector_volume = analysis_constants[
                "analysis_to_collector_volume"
            ]
        except KeyError as error:
            key = error.args[0]
            error.add_note(
                f"'{self.__class__.__name__}' experiment requires '{key}'"
                " to be defined within platform_config.json under 'constants' > 'analysis'."
            )
            self._log(error)
            raise

        slug_check_volume = conditions["slug_check_volume"].set_units("uL", 1)
        if slug_check_volume < slug_volume:
            raise ValueError(
                f"Slug check volume ({slug_check_volume} uL) is lower than slug volume ({slug_volume} uL)."
            )
        if slug_check_volume > sampler_to_reactor_max_volume * 0.95:
            raise ValueError(
                f"Not enough volume between sampler and reactor:\n"
                f"Slug check requires {slug_check_volume} uL while "
                f"available volume is {sampler_to_reactor_max_volume} uL.\n"
                f"Set slug check volume below {sampler_to_reactor_max_volume*0.95} uL or increase the volume."
            )
        # max deviation is given as percentage, but here we use fraction (0 to 1)
        slug_check_max_deviation = (
            conditions["slug_check_max_deviation"].set_units("%", 1) / 100.0
        )
        slug_verification_volume = conditions["slug_verification_volume"].set_units(
            "uL", 1
        )
        slug_verification_threshold = (
            conditions["slug_verification_threshold"].set_units("%", 1) / 100.0
        )

        # Redirecting to waste during reaction requires an additional park loop after the reactor.
        redirect_reactor_to_waste_during_reaction = reaction_constants.get(
            "redirect_reactor_to_waste", True
        )
        if redirect_reactor_to_waste_during_reaction:
            if self._analytical_method is not None:
                reactor_to_analysis_volume += reaction_constants.get(
                    "reactor_slug_park_volume", 0.0
                )
            else:
                reactor_to_collector_max_volume += reaction_constants.get(
                    "reactor_slug_park_volume", 0.0
                )

        # this is the volume which will be pumped into the reactor.
        reaction_volume = (
            slug_volume + reactor_volume + slug_tail_bubble_volume
        )  # volume in uL.
        # total time for the reaction. This is just for the user.
        reaction_time = reaction_volume * 1.0e-3 / reaction_flowrate  # in minutes
        run_time = 20 + reaction_time  # rough estimate
        self._log(
            f"Run [{run_id}]: Estimated run time: {run_time:.1f} min, ends at {time_of_completion(minutes=run_time)}."
        )

        flowrate_gas_sampling = conditions["flowrate_gas_sampling"].with_units("mL/min")
        flowrate_sampling = conditions["flowrate_sampling"].with_units("mL/min")
        flowrate_injection = conditions["flowrate_injection"].with_units("mL/min")
        flowrate_slug_check = conditions["flowrate_slug_check"].with_units("mL/min")
        flowrate_slug_verification = conditions[
            "flowrate_slug_verification"
        ].with_units("mL/min")
        flowrate_delivery = conditions["flowrate_delivery"].with_units("mL/min")
        flowrate_analysis_loading = conditions["flowrate_analysis_loading"].with_units(
            "mL/min"
        )
        flowrate_collection = conditions["flowrate_collection"].with_units("mL/min")

        direct_slug_preparation = conditions["sampling"].value == "direct"

        sampler_recipe, recipe = GenerateComposition.run(
            platform=self._platform,
            experiment_recipe=recipe,
            slug_volume=slug_volume if direct_slug_preparation else slug_volume + 200.0,
            sampler_name="Sampler_cnc",
        )
        sampler_recipe = OrderRecipe.run(
            recipe=sampler_recipe, method=conditions["slug_preparation"].value
        )
        self._log(f"Run [{run_id}]: Set up parameters.", level="ok")

        if self._analytical_method is not None:
            self._analytical_method.sample_loading(enable=False)

        reactor_ready_thread = None
        if inject_slug:
            self._log(f"Run [{run_id}]: Preparing reactor (in the background).")
            self._reactor_prepare(conditions)
            self._reactor_wait_until_slug_can_be_prepared(conditions)
            reactor_ready_thread = Thread(
                target=self._reactor_wait_until_ready,
                name="Check if reactor is ready",
                kwargs={"conditions": conditions},
            )
            reactor_ready_thread.start()

        self._log(f"Run [{run_id}]: Preparing slug...")
        self._redirect_reactor_to_waste(redirect_reactor_to_waste_during_injection)
        # Dry the sampler needle with N2, leave the tail bubble
        MixSlugSampler.run(
            platform=self._platform,
            sampler=self._sampler,
            amplitude=conditions["gas_purging_amplitude"].with_units("uL"),
            flowrate=conditions["gas_purging_flowrate"].with_units("mL/min"),
            cycles=int(conditions["gas_purging_cycles"].value),
            margin_bottom=slug_tail_bubble_volume,
            margin_flowrate=flowrate_gas_sampling,
        )
        # Empty pump
        FillPump.run(pump=self._sampler_pump, fill=False)
        if not direct_slug_preparation:
            # prepare the slug into a vial
            if not inject_slug:
                # If inject_slug is False, collection_vial_id is valid, use that
                # todo here we should leave the slug in the vial, but ok...
                slug_vial = collection_vial_id
            else:
                slug_vial = FindVial.run(
                    platform=self._platform,
                    sampler=self._sampler,
                    vial_type="Sample",
                    nominal_volume=conditions["collection_vial_volume"].with_units(
                        "uL"
                    ),
                    order_by_distance=False,
                )
            PrepareReactionSlug.run(
                platform=self._platform,
                recipe=sampler_recipe,
                sampling_flowrate=flowrate_sampling,
                in_vial=slug_vial,
                slug_volume=slug_volume,
                bubble_volume=0.0,  # bubble is already there!
                bubble_flowrate=flowrate_gas_sampling,
                clean_needle=conditions["rinse"].value > 0.5,
                bubble_between_components=intercomponent_bubble_volume,
            )
        else:
            # Prepare the slug in the loop
            PrepareReactionSlug.run(
                platform=self._platform,
                recipe=sampler_recipe,
                sampling_flowrate=flowrate_sampling,
                bubble_volume=0.0,  # bubble is already there!
                bubble_flowrate=flowrate_gas_sampling,
                clean_needle=conditions["rinse"].value > 0.5,
                bubble_between_components=intercomponent_bubble_volume,
            )
        self._log(f"Run [{run_id}]: Prepared slug.", level="ok")

        if mix_cycles_before_injection > 0:
            self._log(f"Run [{run_id}]: Mixing...")
            # mix the slug in the sampling loop before injection
            MixSlugSampler.run(
                platform=self._platform,
                sampler=self._sampler,
                amplitude=conditions["mix_before_injection_amplitude"].set_units(
                    "uL", 1
                ),
                flowrate=conditions["mix_before_injection_flowrate"].with_units(
                    "mL/min"
                ),
                cycles=mix_cycles_before_injection,
                margin_bottom=slug_head_bubble_volume,
                margin_flowrate=flowrate_gas_sampling,
            )
            self._log(f"Run [{run_id}]: Mixed.", level="ok")

        # If sample should be stored on sampler, transfer it to vial
        FillPump.run(pump=self._sampler_pump, fill=True)
        if not inject_slug:
            self._log(f"Run [{run_id}]: Transferring to vial...")
            PumpSample.run(
                platform=self._platform,
                sample_id=collection_vial_id,
                volume=slug_volume
                + slug_tail_bubble_volume * 0.8
                + slug_head_bubble_volume,
                flowrate=flowrate_sampling,
                delay_after_pumping=conditions["delay_collection"].with_units("S"),
            )
            self._log(
                f"Run [{run_id}]: Transferred to {collection_vial_id}.", level="ok"
            )
            results.success = True
            return

        # Inject the sample
        self._log(f"Run [{run_id}]: Injecting...")
        self._circuit_is_clean = False
        Inject.run(
            platform=self._platform,
            sampler=self._sampler,
            injection_port_name="injection_flow",
            volume=slug_volume
            + slug_tail_bubble_volume
            + slug_head_bubble_volume
            + injection_port_volume,
            flowrate=flowrate_injection,
            sampling_pump=self._sampler_pump,
            retract=True,
            delay_after=conditions["delay_injection"].with_units("S"),
        )
        self._log(f"Run [{run_id}]: Injected.", level="ok")

        # send to mixing chamber and Mix the sample
        PumpVolume.run(
            pump=self._main_pump,
            volume=injection_to_mixing_volume,
            flowrate=flowrate_delivery,
        )
        mixing_chamber_cycles = int(conditions["mix_after_injection_cycles"].value)
        if mixing_chamber_cycles > 0:
            self._log(f"Run [{run_id}]: Mixing...")
            # Since the mixing does some sucking, the collector needle must be disconnected from the waste,
            # as that puts a check-valve in series with the system.
            # Redirecting the reactor is sufficient, but we disconnect the needle in case the redirection valve
            # was not installed.
            self._redirect_reactor_to_waste(
                not redirect_reactor_to_waste_during_reaction
            )
            self._collector["feed"] = self._collector.default_feedrate_z
            self._collector["move"] = self._collector.travel_position
            MixSlug.run(
                pump=self._main_pump,
                amplitude=conditions["mix_after_injection_amplitude"].set_units(
                    "uL", 1
                ),
                flowrate=conditions["mix_after_injection_flowrate"].with_units(
                    "mL/min"
                ),
                cycles=mixing_chamber_cycles,
            )
            Inject.run(
                platform=self._platform,
                sampler=self._collector,
                injection_port_name="injection_waste",
                move_speed=3000.0,
                plunge_speed=200.0,
                volume=0.0,
                flowrate=1.0,
                retract=False,
            )
            self._redirect_reactor_to_waste(redirect_reactor_to_waste_during_reaction)
            self._log(f"Run [{run_id}]: Mixed.", level="ok")

        # Scan the slug geometry and abort run if something went wrong.
        self._log(f"Run [{run_id}]: Checking slug...")
        slug_shape = SlugQualityCheck.run(
            pump=self._main_pump,
            phase_sensor=self._ps_sampler,
            flowrate=flowrate_slug_check,
            pump_volume=slug_check_volume,
            expected_slug_volume=slug_volume,
            max_volume_deviation=slug_check_max_deviation,
        )
        self._log(f"Run [{run_id}]: Slug checked:\n{slug_shape}", level="ok")
        conditions["measured_slug_volume"].value = slug_shape.slug_volume
        conditions["measured_slug_volume"].units = "uL"

        try:
            slug_shape.raise_exception()
        except BadSlugQualityError:
            # Check if the bad slug quality is due to clogging, in which case the platform should *not* restart.
            if len(slug_shape.volumes) <= 1:
                error = CloggingError(
                    "Not enough phase changes detected, this could be caused by clogging!"
                )
                self._log(error)
                raise error
            else:
                self._discard_slug = True
                raise

        # send to reactor
        PumpUntilPhaseChange.run(
            pump=self._main_pump,
            phase_sensor=self._ps_reactor_in,
            flowrate=flowrate_delivery,
            max_volume=(sampler_to_reactor_max_volume - slug_check_volume) * 4,
            wait_for_gas=False,
        )
        FillPump.run(pump=self._main_pump)
        self._redirect_reactor_to_waste(redirect_reactor_to_waste_during_reaction)

        # wait for the reactor to be ready and start the reaction
        self._log(f"Run [{run_id}]: Waiting for reactor to be ready...")
        reactor_ready_thread.join(timeout=reactor_timeout)

        self._start_reactor_monitoring()
        self._log(
            f"Run [{run_id}]: Reaction started ({reaction_time:.1f} minutes"
            f", ends at {time_of_completion(minutes=reaction_time)})..."
        )
        PumpVolume.run(
            pump=self._main_pump, volume=reaction_volume, flowrate=reaction_flowrate
        )
        self._reactor_standby(conditions)
        self._stop_reactor_monitoring()

        # process some reactor data
        if self._reactor_monitoring_data is not None:
            try:
                # look for continuous liquid at least half the size of the slug.
                expected_slug_duration = (
                    slug_volume * 60.0 / (reaction_flowrate * 1000.0)
                )
                measured_residence_time = 0.0
                for index, row in self._reactor_monitoring_data["phase"].iterrows():
                    if (
                        not row["Phase"] == 0
                        and row["Duration"] >= expected_slug_duration * 0.5
                    ):
                        measured_residence_time = row["Time"]
                        break
                self._log(f"Expected slug duration: {expected_slug_duration:.1f} S")
                self._log(
                    f"Measured reactor residence time: {measured_residence_time:.1f} S ({measured_residence_time/60.0:.2f} min)"
                )
                conditions["measured_residence_time"].value = measured_residence_time
                conditions["measured_residence_time"].units = "S"
            except KeyError:
                pass
        self._log(f"Run [{run_id}]: Reaction finished.", level="ok")

        # Here we ensure that the slug can proceed to the analysis or collector, rather than going to waste.
        self._redirect_reactor_to_waste(False)

        # Analysis
        if self._analytical_method is not None:
            FillPump.run(pump=self._main_pump)
            if analysis_phase_sensor is not None:
                # Slug verification: check that we have the slug and not a droplet.
                if slug_verification_volume > 0.0:
                    if self._move_slug_and_verify(
                        run_id=run_id,
                        max_pump_volume=reactor_to_analysis_volume * 1.5,
                        phase_sensor=analysis_phase_sensor,
                        flowrate_delivery=flowrate_delivery,
                        flowrate_verification=flowrate_slug_verification,
                        volume_verification=slug_verification_volume,
                        threshold_verification=slug_verification_threshold,
                    ):
                        analysis_alignment_volume -= slug_verification_volume
                    else:
                        error = DeviceTimeoutError(
                            "Reached the maximum pump volume before phase change event."
                        )
                        self._log(error)
                        raise error
                else:
                    # If slug verification volume is set to 0, do not check.
                    PumpUntilPhaseChange.run(
                        pump=self._main_pump,
                        phase_sensor=analysis_phase_sensor,
                        flowrate=flowrate_delivery,
                        max_volume=reactor_to_analysis_volume * 1.5,
                        wait_for_gas=False,
                    )
            else:
                PumpVolume.run(
                    pump=self._main_pump,
                    volume=reactor_to_analysis_volume,
                    flowrate=flowrate_delivery,
                )
            # The phase sensor is right-outside the device, at this point the analytical device is switched to the
            # loading position and the slug is pushed further.
            self._analytical_method.sample_loading(enable=True)
            try:
                PumpVolume.run(
                    pump=self._main_pump,
                    volume=analysis_alignment_volume,
                    flowrate=flowrate_analysis_loading,
                )
                time.sleep(5)
                self._log(f"Run [{run_id}]: Analysis started...")
                results.result = self._analytical_method.analyse(
                    conditions=conditions,
                    recipe=recipe,
                )
            finally:
                self._analytical_method.sample_loading(enable=False)
            self._log(
                f"Run [{run_id}]: Analysis finished:\n{dict_to_str(results.result)}",
                level="ok",
            )
            reactor_to_collector_max_volume = analysis_to_collector_volume

        # send to collector and collect or discard
        collector_slug_verification_volume = min(
            collector_ps_to_needle_volume, slug_verification_volume
        )
        if collector_slug_verification_volume > 0.0:
            # perform slug verification during delivery
            if self._move_slug_and_verify(
                run_id=run_id,
                max_pump_volume=reactor_to_collector_max_volume * 1.5,
                phase_sensor=self._ps_out,
                flowrate_delivery=flowrate_delivery * 0.75,
                flowrate_verification=flowrate_slug_verification,
                volume_verification=collector_slug_verification_volume,
                threshold_verification=slug_verification_threshold,
            ):
                collector_ps_to_needle_volume -= collector_slug_verification_volume
            else:
                error = DeviceTimeoutError(
                    "Reached the maximum pump volume before phase change event."
                )
                self._log(error)
                raise error
        else:
            # If slug verification volume is set to 0, do not verify.
            PumpUntilPhaseChange.run(
                pump=self._main_pump,
                phase_sensor=self._ps_out,
                flowrate=flowrate_delivery,
                max_volume=reactor_to_collector_max_volume * 1.5,
                wait_for_gas=False,
            )

        collected = False
        if not collection_vial_id == "":
            if self._platform.samples.loc[
                collection_vial_id, "Sampler"
            ] == self._platform.device_id(self._collector):
                self._log(f"Run [{run_id}]: Transferring to vial...")
                collected = True
                PumpSample.run(
                    platform=self._platform,
                    sample_id=collection_vial_id,
                    volume=collector_ps_to_needle_volume
                    + slug_volume
                    + slug_tail_bubble_volume * 0.2,
                    use_pump=self._main_pump,
                    flowrate=flowrate_collection,
                    delay_after_pumping=conditions["delay_collection"].with_units("S"),
                )
                results.collection_vial_id = collection_vial_id
                self._log(
                    f"Run [{run_id}]: Transferred to {GetVialInfo.run(collection_vial_id, self._platform.samples)}.",
                    level="ok",
                )
            else:
                self._log(
                    f"Invalid collector sampler '{self._platform.samples.loc[collection_vial_id, 'Sampler']}'"
                    ", dumping sample."
                )
        if not collected:
            PumpVolume.run(
                pump=self._main_pump,
                volume=slug_volume + slug_tail_bubble_volume,
                flowrate=flowrate_delivery,
            )
        # Success == True only if we reached all the way to the end of the experiment procedure.
        # if the analysis result has a 'pass' attribute, we set the run.success to this value. This is in case the
        # analysis technically succeeded (no exception raised), but the data obtained should be discarded by the ML.
        # The crude and the analysis results are stored for manual review.
        if results.result is not None:
            results.success = results.result.get("pass", True)
        else:
            results.success = True

    def _procedure_cleanup(self) -> None:
        try:
            cleaning_constants = self._platform_constants["cleaning"]
        except KeyError as error:
            error.add_note(
                f"'{self.__class__.__name__}' experiment requires a 'cleaning' section"
                " to be defined within platform_config.json under 'constants'."
            )
            self._log(error)
            raise
        try:
            # Redirect to waste during injection?
            redirect_reactor_to_waste = cleaning_constants.get(
                "redirect_reactor_to_waste", False
            )
            # Volume of cleaning agent to use
            cleaning_agent_volume = cleaning_constants.get("cleaning_agent_volume", 0.0)
            # Volume of carrier solvent to use to wash the whole system
            platform_wash_volume = cleaning_constants["platform_wash_volume"]
            platform_wash_volume_on_slug_fail = cleaning_constants[
                "platform_wash_volume_on_slug_fail"
            ]
            platform_wash_flowrate = cleaning_constants["platform_wash_flowrate"]
            # Volume of carrier solvent to use to wash the injection port and the sampling loop
            injection_wash_volume = cleaning_constants["injection_wash_volume"]
            injection_wash_flowrate = cleaning_constants["injection_wash_flowrate"]
            # Volume of gas to use to purge the injection port and remove liquid after the wash
            gas_purge_volume = cleaning_constants["gas_purge_volume"]
            gas_purge_flowrate = cleaning_constants["gas_purge_flowrate"]
            # Volume of carrier solvent dumped into the waste injection port to clean the needle
            # and ensure no gas is left in it
            needle_wash_volume = cleaning_constants["needle_wash_volume"]
            needle_wash_flowrate = cleaning_constants["needle_wash_flowrate"]
            # Additional time to wait in S after system has been purged of liquid
            drying_time = cleaning_constants["drying_time"]
            drying_time_on_slug_fail = cleaning_constants["drying_time_on_slug_fail"]

        except KeyError as error:
            key = error.args[0]
            error.add_note(
                f"'{self.__class__.__name__}' experiment requires '{key}'"
                " to be defined within platform_config.json under 'constants' > 'cleaning'."
            )
            self._log(error)
            raise

        # Check if a vial with cleaning agent was defined and is available.
        # If such vial was never defined, proceed without cleaning agent.
        cleaning_agent_vial = None
        # noinspection PyTypeChecker
        if (
            any(self._platform.samples["Type"] == "CleaningAgent")
            and cleaning_agent_volume > 0.0
        ):
            # At least one cleaning agent vial was defined. This means that the user wants to use it.
            cleaning_agent_vial = FindVial.run(
                platform=self._platform,
                sampler=self._sampler,
                vial_type="CleaningAgent",
                ensure_volume=-cleaning_agent_volume,
            )

        # Reset samplers and pumps
        if self._analytical_method is not None:
            self._analytical_method.sample_loading(enable=False)
        run_all(
            HomeSampler.get_thread(sampler=self._sampler),
            HomeSampler.get_thread(sampler=self._collector),
            FillPump.get_thread(pump=self._main_pump),
            FillPump.get_thread(
                pump=self._sampler_pump, fill=cleaning_agent_vial is None
            ),
        )
        # place collector in 'resting' position
        Inject.run(
            platform=self._platform,
            sampler=self._collector,
            injection_port_name="injection_waste",
            move_speed=3000.0,
            plunge_speed=200.0,
            volume=0.0,
            flowrate=1.0,
            retract=False,
        )
        if not self._circuit_is_clean:
            self._redirect_reactor_to_waste(redirect_reactor_to_waste)

            # If a cleaning agent was defined, pick that up here.
            if cleaning_agent_vial is not None:
                PumpSample.run(
                    platform=self._platform,
                    sample_id=cleaning_agent_vial,
                    volume=-cleaning_agent_volume,
                    flowrate=1.0,
                    delay_after_pumping=0.5,
                )
                injection_wash_volume += cleaning_agent_volume

            # clean injection port and flush the sampling loop.
            Inject.run(
                platform=self._platform,
                sampler=self._sampler,
                injection_port_name="injection_flow",
                volume=injection_wash_volume,
                flowrate=injection_wash_flowrate,
                retract=True,
            )
            # purge the injection port with gas.
            # this gives a cleaner slug profile on the next slug injection.
            gas_vial = FindVial.run(
                platform=self._platform,
                sampler=self._sampler,
                vial_type="Gas",
            )
            if gas_vial is None:
                error = NoSuitableVialError(
                    f"No viable 'Gas' vial available on '{self._sampler}'",
                    vial_type="Gas",
                )
                self._log(error)
                raise error
            FillPump.run(pump=self._sampler_pump, fill=False)
            PumpSample.run(
                platform=self._platform,
                sample_id=gas_vial,
                volume=-gas_purge_volume,
                flowrate=gas_purge_flowrate,
                needle_position=0.3,
                update_volume=False,
            )
            Inject.run(
                platform=self._platform,
                sampler=self._sampler,
                injection_port_name="injection_flow",
                volume=gas_purge_volume * 0.4,
                flowrate=gas_purge_flowrate,
                retract=True,
                delay_after=5.0,
            )
            Inject.run(
                platform=self._platform,
                sampler=self._sampler,
                injection_port_name="injection_flow",
                volume=gas_purge_volume * 0.6,
                flowrate=gas_purge_flowrate,
                retract=True,
                delay_after=5.0,
            )
        # clean the needle (this is done on the background, as we do not need the sampler for anything else).

        def clean_needle():
            FillPump.run(pump=self._sampler_pump)
            Inject.run(
                platform=self._platform,
                sampler=self._sampler,
                injection_port_name="injection_waste",
                volume=needle_wash_volume,
                flowrate=needle_wash_flowrate,
                retract=True,
            )
            CleanNeedle.run(
                platform=self._platform,
                sampler=self._sampler,
                purge_volume=0.0,
                purge_flowrate=2.0,
            )

        clean_needle_thread = ThreadEx(
            target=clean_needle, name="Cleaning sampler needle"
        )
        clean_needle_thread.start()

        if not self._circuit_is_clean:
            # flush reactor system
            if self._discard_slug:
                platform_wash_volume = platform_wash_volume_on_slug_fail
                drying_time = drying_time_on_slug_fail
            else:
                # Clean the rest of the system only if it was not a slug fail.
                self._redirect_reactor_to_waste(False)
            ConnectInjectionPort.run(
                platform=self._platform,
                sampler=self._sampler,
                port_name="injection_flow",
                inject=False,
            )
            PumpVolume.run(
                pump=self._main_pump,
                volume=platform_wash_volume,
                flowrate=platform_wash_flowrate,
                allow_refill=True,
            )
            run_all(
                Thread(
                    target=self._dry_system,
                    name="Drying system with n2",
                    kwargs={"drying_time": drying_time},
                ),
                FillPump.get_thread(pump=self._main_pump, fill=True),
            )
            self._circuit_is_clean = True

        # Make sure the cleaning of the needle is finished (and raise any exceptions)
        clean_needle_thread.join(timeout=10 * 60)
        clean_needle_thread.raise_exception()

        self._discard_slug = False

    def _dry_system(
        self,
        drying_time: float = 60.0,
        timeout: float = 10 * 60,
        update_interval: float = 1.0,
    ) -> None:
        """
        Open the nitrogen gas valve until the whole line is filled with gas.
        Checks the last phase sensor to ensure there is no liquid left.

        @param drying_time: float = 30.0
            Additional time in S to run gas in the system after it has been completely purged.
        @param timeout: float = 10*60
            Max time to wait for dry condition.
        @param update_interval: float = 1.0
            Check phase sensor every this many seconds.
        """
        # Purge for a minimum of time.
        # This makes sure we are not just detecting the tail bubble after the slug.
        self._n2_valve["valve"] = "open"
        try:
            time.sleep(60.0)

            last_time_liquid = time.time()
            current_time = last_time_liquid
            while current_time - last_time_liquid < drying_time:
                time.sleep(update_interval)
                current_time = time.time()
                if self._ps_out["phase"].is_liquid():
                    last_time_liquid = current_time
                if current_time - last_time_liquid > timeout:
                    error = RuntimeError(
                        "Attempts at clearing the system of liquids have failed,"
                        " check for clogging and make sure the N2 valve is operating correctly."
                    )
                    self._log(error)
                    raise error
            time.sleep(drying_time)
        finally:
            self._n2_valve["valve"] = "close"
