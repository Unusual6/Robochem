"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr: The backend class for the platform, this will be the only bit that interacts with the actual platform,
is initialised at the beginning of the streamlit run and will be used to store info about the experiments and the platform
once built.


"""

import json
import os

import pandas as pd
import sys
from itertools import product
from robrains.base_classes import BaseLoggedClass
from streamlit.runtime.state import SessionStateProxy
from streamlit import session_state


from robrains.parameter_backends import (
    Chemical,
    ML_parameter,
    PhysicalParameter,
    AnalyParameter,
    ExpParameter,
)
from robrains.session_management import SessionContainer
from backend.ml_backends import (
    SingleBayesianOpti,
    SingleBayesianOptiHITL,
    EfficientBatchedBO_HITL,
    MultiTaskScope,
    MultiTaskScope_HITL,
    EnantioExtravaganza,
    DevHITL,
    ScopeAcceleratorTask,
    MyCustomML,
    DragonflyML,
)
from omniplatypus.procedures.analytics.analytics_template import AnalyticsTemplate

from omniplatypus.procedures.experiments.photochemistry import (
    PhotochemicalReaction,
    PhotochemicalReactionDryRun,
)
from omniplatypus.procedures.experiments.thermochemistry import ThermochemicalReaction
from omniplatypus.procedures.experiments.base_experiment import (
    NumericalParameter,
    ExperimentalParameter,
    BaseExperiment,
)
from threading import Event


class PlatformBackend(BaseLoggedClass):
    """Class inherits from BaseLoggedClass for logging purposes
    The idea here is that this is the piece of code that interacts with the platform. At init (which should be done
    as soon as the streamlit app is started) it will load the platform config, so then the user choices are
    funnelled in a way that makes sense. this will also store the sample and experiments, the streamlit session state to
    access values. This will also take care of saving things when needed

    Members:
        platform_config_path: str, path to the platform_config.json file for the platform
        holder_config_path: str, path to the sample_holder_types.json file of the platform
        platform_user_path:
        robochem_path:
        chemical_parameter:
        analytical_parameter:
        ML_classes:
        _rolling:
        _emergency_stop:
        _ml_ready:
        _platform_ready:
        session:
        session_container
        platform_config
        visualisation
        available_experiments
        ml_experiment_class
        platform_experiment_class
        platform_experiment
        platform_thread
        ml_thread



    Methods:
        __init__(self, streamlit_session: SessionStateProxy)->None
        available_platforms(self)->list
        platform_available_experiments(self, platform_name: str)->list
        platform_available_physical_parameters(self, platform_name: str)

    """

    # Use __file__ to construct absolute path (works regardless of cwd)
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    platform_config_path = os.path.join(
        _base_dir, "OmniPlatypus", "OmniPlatypus", "omniplatypus", "config", "platform_config.json"
    )
    holder_config_path = os.path.join(
        _base_dir,
        "OmniPlatypus",
        "OmniPlatypus",
        "omniplatypus",
        "config",
        "sample_holder_types.json",
    )
    # figure out the base path of the system:
    platform_user_path = os.path.expanduser("~")
    robochem_path = os.path.join(platform_user_path, "Robochem")
    # give the template to the chemical class for each chemical parameter
    chemical_parameter = Chemical
    physical_parameter = PhysicalParameter
    experimental_parameter = ExpParameter
    analytical_parameter = AnalyParameter
    ml_parameter = ML_parameter
    ML_classes = {
        "BO_optimisation": SingleBayesianOpti,
        "BO_optimisation_HITL": SingleBayesianOptiHITL,
        "EfficientBatchedBO_HITL": EfficientBatchedBO_HITL,
        "MultiTaskScope": MultiTaskScope,
        "MultiTaskScope_HITL": MultiTaskScope_HITL,
        "ScopeAcceleratorTask": ScopeAcceleratorTask,
        "EnantioExtravaganza": EnantioExtravaganza,
        "MyCustomML": MyCustomML,
        "DragonflyML": DragonflyML,
    }
    platform_constructors = {
        "PhotochemicalReaction": PhotochemicalReaction,
        "ThermochemicalReaction": ThermochemicalReaction,
        "PhotochemicalReaction - dry run": PhotochemicalReactionDryRun,
    }

    _rolling = Event()
    _emergency_stop = Event()
    _ml_ready = False
    _platform_ready = False
    _results_df = None
    platform_experiment: BaseExperiment | None = None

    def __del__(self):
        try:
            if self.platform_experiment is not None:
                self.platform_experiment.stop()
        except:
            pass

    def __init__(self, streamlit_session: SessionStateProxy) -> None:
        """Initialises the platform backend"""

        self.ml_experiment_class = None
        self.assertion_method(
            streamlit_session,
            lambda x: isinstance(x, SessionStateProxy),
            "streamlit_session is not a streamlit session",
        )
        self.session = streamlit_session
        # TODO: Check this one, otherwise we get circular imports problems
        self.session_container = SessionContainer(streamlit_session)
        self.session_container.do_not_save += [
            "platform_error_condition",
            "fixing_platform_df",
        ]
        with open(self.platform_config_path, "r") as f:
            self.platform_config = json.load(f)

        # check if the robochem path exists, if not create it
        if not os.path.exists(self.robochem_path):
            os.makedirs(self.robochem_path)
            self.log_mssg(
                f"Created the robochem path at {self.robochem_path}", level="ok"
            )
        # dummy visualisation object, will need to make this a proper one
        self.visualisation = lambda x: self.session.write(x)
        self.platform_experiment = None

    @property
    def available_platforms(self) -> list:
        """returns the available platforms as a list
        :returns: list of available platforms i.e. ['Perry', 'Jerry', 'Terry']"""
        if self.platform_config is None:
            return []
        return list(self.platform_config.keys())

    def platform_available_experiments(self, platform_name: str) -> list:
        """returns the available experiments for a given platform
        :platform_name: str:
            keyword name of the platform to get the available experiments for, must be in available_platforms
        :returns list of available experiments for the platform i.e. ['exp1', 'exp2', 'exp3']
        """
        self.assertion_method(
            platform_name,
            lambda x: x in self.available_platforms,
            "platform_name must be in available_platforms",
        )
        self.assertion_method(
            self.platform_config[platform_name],
            lambda x: "Gui_Specs" in x and x["Gui_Specs"],
            "No experiments available for this platform",
        )
        self.assertion_method(
            self.platform_config[platform_name]["Gui_Specs"],
            lambda x: "Supported_Experiments" in x and x["Supported_Experiments"],
            "No experiments available for this platform",
        )
        self.available_experiments = self.platform_config[platform_name]["Gui_Specs"][
            "Supported_Experiments"
        ]

        return [
            item
            for item in self.platform_constructors.keys()
            if item in self.available_experiments
        ]

    def _parse_values(self, parameter):
        """given a omniplatipus experimental or numerical parameter object it parses out the values in a dict:
        :parm parameter: object: the parameter object to parse (NumericalParameter or ExperimentalParameter)
        :
        :returns dict: the parsed values in a dictionary
        """

        if isinstance(parameter, NumericalParameter):
            return {
                "min_value": parameter.min_value,
                "max_value": parameter.max_value,
                "unit": parameter.units,
                "value": parameter.value,
            }
        elif isinstance(parameter, ExperimentalParameter):
            return {
                "allowed_values": parameter.allowed_values,
                "value": parameter.value,
            }
        else:
            return {}

    def platform_parameters(
        self,
        experiment_name: str,
        required: bool = True,
        parameter_type: str = "numerical",
    ):
        """
        Returns the parameters for a given experiment on a given platform.

        :param experiment_name: Name of the experiment.
        :param required: If True, returns required parameters; if False, returns optional parameters.
        :param parameter_type:
            - 'numerical': Returns only numerical parameters.
            - 'non_numerical': Returns only non-numerical parameters.
            - 'both': Returns both numerical and non-numerical parameters as two separate dictionaries.
        :return: A dictionary of parameters filtered by the specified criteria, or two dictionaries if 'both' is selected.
        """
        # Look for the experiment in the experiment constructors:
        if experiment_name in self.platform_constructors:
            experiment_class: BaseExperiment = self.platform_constructors[
                experiment_name
            ]

            # Select the appropriate parameters based on the 'required' flag
            parameters = (
                experiment_class.get_required_parameters()
                if required
                else experiment_class.get_optional_parameters()
            )

            # Filter and return parameters based on the 'parameter_type' argument
            if parameter_type == "numerical":
                return {
                    param.name: self._parse_values(param)
                    for param in parameters
                    if isinstance(param, NumericalParameter)
                }
            elif parameter_type == "non_numerical":
                return {
                    param.name: self._parse_values(param)
                    for param in parameters
                    if not isinstance(param, NumericalParameter)
                }
            elif parameter_type == "both":
                numerical_params = {
                    param.name: self._parse_values(param)
                    for param in parameters
                    if isinstance(param, NumericalParameter)
                }
                non_numerical_params = {
                    param.name: self._parse_values(param)
                    for param in parameters
                    if not isinstance(param, NumericalParameter)
                }
                return numerical_params, non_numerical_params
        return {}

    def platform_available_physical_parameters(self, platform_name: str):
        """returns the available pysical parameters for a given platform.
        :platform_name: str:
            keyword name of the platform to get the available physical parameters for, must be in available_platforms

        :returns a dictionary of the available physical parameters for the platform i.e. {'param1': {'min': 0, 'max': 10, 'unit': 'mL'}}
        """

        self.assertion_method(
            platform_name,
            lambda x: x in self.available_platforms,
            "platform_name must be in available_platforms",
        )
        self.assertion_method(
            self.platform_config[platform_name],
            lambda x: "Gui_Specs" in x and x["Gui_Specs"],
            "No physical parameters available for this platform",
        )
        self.assertion_method(
            self.platform_config[platform_name]["Gui_Specs"],
            lambda x: "Supported_Parameters" in x and x["Supported_Parameters"],
            "No physical parameters available for this platform",
        )

        # drop the tags key in each sub dictionary
        return {
            k: {k1: v1 for k1, v1 in v.items() if k1 != "tags"}
            for k, v in self.platform_config[platform_name]["Gui_Specs"][
                "Supported_Parameters"
            ].items()
        }

    def get_the_sampler_holders(self, platform_name: str, keyword: str):
        """
        Search amongst the platform for the liquid handlers and returns the liquid handler and it's sample holders
        :param platform_name: str: the name of the platform to search in
        :param keyword: str: the keyword to search for

        returns: subset of dictionary of items that have the keyword in the value
        """
        try:
            keys = {
                key: {
                    loc: ation
                    for loc, ation in value["setup"]["locations"].items()
                    if ation["type"] == "holder"
                }
                for key, value in self.platform_config[platform_name]["devices"].items()
                if value.get("tags", None) is not None and "handler" in value["tags"]
            }

            if len(keys) == 0:
                self.log_mssg(f"No values found with tag {keyword}", level="warning")

            return keys
        except Exception as e:
            self.log_mssg(f"Error searching by tag: {e}", level="error")
            return {}

    def sample_holder_positions(self, holder_config: dict):
        """returns a list of the available positions in the holder configuration:
        :holder_config: dict: the holder configuration dictionary (from the holder config file)
        """

        list = holder_config.get("components", None)
        if list is None:
            self.log_mssg(
                f"No components found in the holder configuration", level="error"
            )
            return []
        alphabetic = [key for key in list.keys() if key.isalpha()]
        numeric = [key for key in list.keys() if key.isnumeric()]

        prod = [a + n for a, n in product(alphabetic, numeric)]

        return prod

    def get_handlers(self, platform_name: str):
        """returns the liquid handlers available to the platform, this retunrs a dictionary, with the
        handler name as the key, the handler sample holders as the value
        :param platform_name: str: the name of the platform to get the handlers for

        returns: dict: the handlers available to the platform, removes some stuff too in oder to return the following
        {'handler1':{holder1: [A1, A2, A3....], holder3:[...]},'handler2: [{holderG: [A1, A2, A3....]}]}
        """

        # Assert platform_name is valid
        if platform_name not in self.available_platforms:
            self.log_mssg("platform_name must be in available_platforms", level="error")
            return {}

        # Retrieve handlers based on platform_name and tag
        handlers = self.get_the_sampler_holders(platform_name, "handler")
        # Load the holder configuration from a file
        with open(self.holder_config_path, "r") as f:
            holder_config = json.load(f)

        # Initialize the result dictionary
        handlers_dict = {}

        try:
            # iterate over each handler:
            for handler, holders in handlers.items():
                # initialize the holder dictionary
                holder_dict = {}
                # iterate over each holder:
                for holder, holder_data in holders.items():
                    # get the holder positions
                    positions = self.sample_holder_positions(
                        holder_config[holder_data.get("shape")]
                    )
                    holder_dict[holder] = positions
                handlers_dict[handler] = holder_dict

        except Exception as e:
            self.log_mssg(f"Error processing handlers: {e}", level="error")

        return handlers_dict

    def get_analytics(self):
        """
        returns the available analytics for the experiments
        """
        # first get the experiment class:
        experiment_name = self.session_container["platform_experiment"]
        if experiment_name in self.platform_constructors:
            experiment_class: BaseExperiment = self.platform_constructors[
                experiment_name
            ]
            return experiment_class.get_analytical_methods().keys()
        else:
            raise RuntimeError(
                f"Cannot find definition for experiment '{experiment_name}'."
            )

    def get_analytic_parameters(self):
        """
        returns the available analytics for the experiments
        """
        # first get the chosen analytics class:
        analytics_name = self.session_container.get("analysis_type", None)
        if analytics_name is None:
            self.log_mssg(f"Analysis technique not found", level="warning")
            return None
        experiment_name = self.session_container["platform_experiment"]
        if experiment_name in self.platform_constructors:
            available_analytics = self.platform_constructors[
                experiment_name
            ].get_analytical_methods()
        else:
            self.log_mssg(f"Experiment {experiment_name} not found", level="warning")
            return None

        if analytics_name in available_analytics.keys():
            analytics_class: AnalyticsTemplate = available_analytics[
                analytics_name
            ].analysis_class
            if (
                analytics_class is None
                or "HITL" in self.session_container["experiment_type"]
            ):
                self.log_mssg(
                    f"Analytics {analytics_name} must be a human in the loop type",
                    level="ok",
                )
                return []
        else:
            self.log_mssg(f"Analytics {analytics_name} not found", level="warning")
            return None

        # we have decided that if parameters have tag None these should not be seen by the user and
        # handled by the backend
        required_parameters_frontend = [
            param
            for param in analytics_class.get_required_parameters()
            if param.tag is not None
        ]
        optional_parameters_frontend = [
            param
            for param in analytics_class.get_optional_parameters()
            if param.tag is not None
        ]
        required_parameters_machine = [
            param
            for param in analytics_class.get_required_parameters()
            if param.tag is None
        ]
        optional_parameters_machine = [
            param
            for param in analytics_class.get_optional_parameters()
            if param.tag is None
        ]

        self.parameter_machine = (
            required_parameters_machine + optional_parameters_machine
        )

        return (
            required_parameters_frontend,
            optional_parameters_frontend,
            analytics_class.get_processing_method_names(),
        )

    def initialise_ML(self):
        """initialises the ML backend, this will be used to run the ML experiments
        reads from the ML class the required data and initialises the class"""
        # now priming is different, we do ML_prime, then com_prime, then run and the thread will start
        # initialise the ML class
        # for priming we need: list of ml_parameters, list of objectives, list of constants
        # and path to save the results
        list_of_ml_parameters = [
            self.session_container[name]
            for name in self.session_container.search_by_tag("ML_parameter")
        ]
        list_of_objectives = self.session_container["objectives"]
        list_of_physical_constants = [
            self.session_container[name]
            for name in self.session_container.search_by_tag("physical_parameter")
            if self.session_container[name].style == "constant"
        ]
        list_of_experimental_constants = [
            self.session_container[name]
            for name in self.session_container.search_by_tag("experimental_parameter")
        ]
        list_of_chemical_constants = [
            self.session_container[name]
            for name in self.session_container.search_by_tag("chemical_parameter")
            if self.session_container[name].purpose == "constant"
        ]
        list_of_analytical_constants = [
            self.session_container[name]
            for name in self.session_container.search_by_tag("analytical_parameter")
        ]
        list_of_constants = (
            list_of_physical_constants
            + list_of_chemical_constants
            + list_of_analytical_constants
            + list_of_experimental_constants
        )
        self.handle_parameter_machine()
        # get the path to save the results
        path = self.session_container["experiment_path"]
        # check first if the ml_experiment has been primed:
        if self.ml_experiment_class is None:
            self.ml_experiment_class = self.session_container["ml_experiment_class"]
        if self.ml_experiment_class.primed == True:
            # check if the ML has an instance of the experiment class available:
            if self.ml_experiment_class.experiment != self.platform_experiment:
                self.ml_experiment_class.experiment = self.platform_experiment
            if sorted(self.ml_experiment_class.constants) != sorted(list_of_constants):
                self.ml_experiment_class.constants = list_of_constants

            self.ml_experiment_class.parameter_machine = self.parameter_machine
            self.ml_experiment_class.run()
            self.log_mssg(f"ML Backend already primed", level="ok")
            return
        if self._platform_ready == False:
            self.log_mssg(f"Platform not ready, cannot initialise ML", level="error")
            return
        try:
            # run the ML prime method:
            self.ml_experiment_class.ML_prime(
                ML_parameters=list_of_ml_parameters,
                targets=list_of_objectives,
                save_path=path,
            )

            # now do the com_prime
            self.ml_experiment_class.com_prime(
                constants=list_of_constants,
                experiment=self.platform_experiment,
                parameter_machine=self.parameter_machine,
            )
            self.ml_experiment_class.run()
            self._ml_ready = True
            self.log_mssg(
                message=f"Successfully initialised the ML {self.ml_experiment_class}",
                level="ok",
            )

        except Exception as e:
            self.log_mssg(f"Error initialising the ML backend: {e}", level="error")
            raise e
            self._ml_ready = False

    def handle_parameter_machine(self):
        """this function has the purpose of preparing the parameter machine for the ML backend

        for now: the only thing we need to change is give a base_name and the position for the data

        """
        if not hasattr(self, "parameter_machine"):
            self.parameter_machine = []
        for param in self.parameter_machine:
            match param.name:
                case "sample_name":
                    param.value = self._generate_base_name()
                case "data_folder":
                    param.value = self._generate_data_folder(param.value)
                case _:
                    pass
                    # TODO: add more case as needed

    def _generate_base_name(self):
        """generates a base name for the experiment by taking the user name and the experiment name

        returns: a lambda function that takes the run name and returns the full name
        """
        user_name = self.session_container["user_name"]
        experiment_name = self.session_container["experiment_name"]
        return lambda run_name: f"{user_name}_{experiment_name}_{run_name}"

    def _generate_data_folder(self, base_folder: str):
        """makes a data folder for the data

        :param base_folder: str: the base folder to save the data in a new folder will be made there
        subdivided by the user name and the experiment name

        """
        user_name = self.session_container["user_name"]
        experiment_name = self.session_container["experiment_name"]
        platform_name = self.session_container["platform_name"]
        path = os.path.join(base_folder, platform_name, user_name, experiment_name)

        os.makedirs(
            path,
            exist_ok=True,
        )
        return path

    def unmerge_dfs(self, merged_df: pd.DataFrame):
        """
        Splits the merged DataFrame into 'StockDF' and 'VialDF'.

        Parameters:
            merged_df (pd.DataFrame): The merged DataFrame with the configuration as shown in the `merge_dfs` function.

        Returns:
            VialDF, StockDF.
        """

        # Reset the index to get 'VialID' back as columns
        merged_df = merged_df.reset_index()

        # Extract VialDF
        vial_df_columns = [
            "VialID",
            "VialName",
            "Volume",
            "Type",
            "Sampler",
            "Holder",
            "Position",
            "Solvent",
            "StockID",
        ]
        vial_df = merged_df[vial_df_columns]

        return vial_df

    def merge_dfs(self, stocks: pd.DataFrame = None, vials: pd.DataFrame = None):
        """
        Merges 'StockDF' and 'VialDF to have the cofiguration as in example:
                            Conc_A  Volume Type   Sampler      Holder   Position   Solvent StockID
        VialID VialName
        hexID  N2           0.0     0.0     Gas  Sampler_cnc  holder_B       A1   Nonw     None
        hexID  Waste_1      0.0     0.0   Waste  Sampler_cnc  holder_F       A1   None     None
        hexID  Solvent_1    0.0     0.0  Solvent Sampler_cnc  holder_F       A3   ACN      Solvent
        hexID  Sample_1     0.0     0.0  Sample  Sampler_cnc  holder_C       A1   None
        hexID  Cleaning_1   0.0     0.0   Waste  Sampler_cnc  holder_F       A1   ACN

        :params:
        stocks and vials, are the DF. but ignore them, i use them for debugging purposes
        Returns:
            pd.DataFrame: Merged DataFrame with the configuration as shown above.
        """

        # Get the DataFrames from the session container
        stocks = stocks if stocks is not None else self.session_container["StockDF"].df
        vials = vials if vials is not None else self.session_container["VialDF"].df

        merged = pd.merge(vials, stocks, on="StockID", how="left")
        conc_cols = [col for col in merged.columns if "Conc" in col]
        merged[conc_cols] = merged[conc_cols].fillna(0)

        # print(merged)

        def handle_solvent(row):
            if pd.isna(row["Solvent"]):
                if row["StockID"] == "Not a Stock":
                    return None
                else:
                    return row["StockID"]
            return row["Solvent"]

        merged["Solvent"] = merged.apply(lambda row: handle_solvent(row), axis=1)
        merged.set_index("VialID", inplace=True, verify_integrity=True)

        return merged.copy()

    def initialise_platform(self):
        """Initialises the platform based on the experiment chosen by the user.
        Experiments in the platform we built should always have a required_data attribute that is a list
        of the data required to run the experiment. Then the experiment class is initialised, the experiment will know
        what to do for its own initialisation.

        we run the experiment initialisation in a separate thread
        """
        try:
            # find out which experiment method we are running and initalise the class:
            experiment_key = self.session_container["platform_experiment"]
            self.platform_experiment_class = self.platform_constructors[experiment_key]
            # initialise the experiment class
            self.platform_experiment = self.platform_experiment_class(
                analytical_method=self.session_container["analysis_type"],
            )
            # find the name of the platform :
            platform_name = self.session_container["platform_name"]
            # get the DFA for the platform:
            samples_df = self.merge_dfs()

            # start the experiment:
            # optional arguments for Platform object, see Omniplatypus Platform.build() for details.
            ### this is a stupid workaround. MacOS requires the GUI to be opened in the main thread.
            ### which stops the plastform launch, so i'm not opening the gui whern i run the code on mac:
            gui_open = sys.platform.startswith("win")
            platform_args = {
                "open_gui": gui_open,
                "allow_slack_messages": False,
            }
            override_constants = None
            if session_state.platform_start_skip_cleaning:
                override_constants = {"cleaning": {"clean_on_start": False}}
            self.platform_experiment.start(
                platform_name=platform_name,
                samples=samples_df,
                platform_build_arguments=platform_args,
                override_platform_constants=override_constants,
                file_storage_root=self.session_container["experiment_path"],
            )

            self._platform_ready = True
            self.log_mssg(
                message=f"Successfully initialised the platform experiment {self.platform_experiment}",
                level="ok",
            )
        except Exception as e:
            self.log_mssg(
                message=f"Platform initialisation errored: {e} NOT READY", level="error"
            )
            self._platform_ready = False
            raise e

    def start(self):
        """initialises the ML side, initialises the platform, decides the first experiments, runs them, then
        used the ML_backend to run further experiment, handles saving, basically is the central function when
        user clicks run on the GUI. (this will be a thread mess)
        """
        # initialise the queues as needed:

        # initialise the ML backend and platform:

        if not self._platform_ready:
            self.initialise_platform()
        else:
            self.platform_experiment.resume()
            self.log_mssg("Platform resumed")
        if not self._ml_ready:
            self.initialise_ML()
        self._rolling.set()

    def pause(self):
        """
        Pause runs on the platform.
        """
        self.platform_experiment.pause()
        self._rolling.clear()
        self.log_mssg("Paused the platform")

    def stop(self):
        """stops the platform after the current run"""
        self._rolling.clear()
        self._emergency_stop.set()
        self.platform_experiment.stop()

        del self.platform_experiment
        self._platform_ready = False
        self._ml_ready = False

        self.log_mssg("Stopped the platform")

    def validate_data(self):
        """Checks that all the required components of the data are initialised and ready to roll"""
        # check that there is at least a chemical:
        if len(self.session_container.search_by_tag("chemical")) == 0:
            self.log_mssg("No chemical data found", level="error")
            self._ready_to_roll = False
            return "No chemical data found"
        # check that there is at least on ML parameter:
        if len(self.session_container.search_by_tag("ML_parameter")) == 0:
            self.log_mssg("No ML data found", level="error")
            self._ready_to_roll = False
            return "No ML data found"
        # check that the vial and liquid handler dfs are not empty:
        if len(self.session_container["VialDF"].df) == 0:
            self.log_mssg("No vial data found", level="error")
            self._ready_to_roll = False
            return "No vial data found"
        if len(self.session_container["StockDF"].df) == 0:
            self.log_mssg("No stock data found", level="error")
            self._ready_to_roll = False
            return "No stock data found"

        # add more checks as needed

        self._ready_to_roll = True
        return None

    @property
    def ready_to_roll(self):
        """
        checks that everything is in order, all the parameters are set correctly, and the system is ready to start
        """
        return self._ready_to_roll

    @property
    def rolling(self):
        """returns true when the platform is running an experiment"""
        return self._rolling

    def __del__(self):
        if hasattr(self, "ml_experiment_class"):
            self.ml_experiment_class.kill_thread()
