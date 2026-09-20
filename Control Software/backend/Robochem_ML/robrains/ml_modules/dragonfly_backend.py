"""
Dragonfly GP Bandit ML Backend

Bayesian Optimization backend using the dragonfly-opt library.
Uses the EuclideanGPBandit optimiser via its ask/tell interface.

Reference: https://github.com/dragonfly/dragonfly
"""

import sys
import time
from typing import Any, Optional, Tuple

import numpy as np
import pandas as pd
import torch

# Add dragonfly source to path (dragonfly-opt uses numpy.distutils which is
# incompatible with NumPy >= 1.26, so we import directly from source).
_DRAGONFLY_PATH = "/home/jpf/ai4s/dragon/dragonfly"
if _DRAGONFLY_PATH not in sys.path:
    sys.path.insert(0, _DRAGONFLY_PATH)

from dragonfly.exd.domains import EuclideanDomain
from dragonfly.exd.experiment_caller import EuclideanFunctionCaller
from dragonfly.opt.gp_bandit import (
    EuclideanGPBandit,
    get_all_euc_gp_bandit_args,
)
from dragonfly.utils.option_handler import load_options

from robrains.communication_module import baseMLBackend
from robrains.utils import ColumnNormalizer


class DragonflyBackend(baseMLBackend):
    """
    Dragonfly GP Bandit Backend

    Bayesian Optimization backend that uses dragonfly's EuclideanGPBandit
    optimiser with the ask/tell interface. Dragonfly uses Gaussian Processes
    as surrogate models and supports multiple acquisition functions (TS, UCB, EI).

    Key methods:
    - validate_and_update: Validate and update parameters from frontend
    - first_run: Generate initial experimental points
    - update: Core optimization loop (tell dragonfly results, ask for next point)
    """

    # Define parameters that can be configured from the frontend
    input_parameters = {
        "Number of initial points": "int",
        "Number of total points": "int",
        "Number of Experiments per batch": "int",
        "Acquisition Function": ["ts", "ucb", "ei"],
        "Termination criterion": ["max_iter", "performance"],
        "Resubmission of Failed N": "int",
    }

    # Default values for the parameters
    input_defaults = {
        "Number of initial points": 10,
        "Number of total points": 100,
        "Number of Experiments per batch": 1,
        "Acquisition Function": "ucb",
        "Termination criterion": "max_iter",
        "Resubmission of Failed N": 0,
    }

    _bound_adjustment_method = "None"

    def __init__(self):
        super().__init__()
        self._optimiser = None
        self._n_told = 0

    def validate_and_update(self, key: str, value: Any) -> None:
        """
        Validate and update parameters from the frontend.

        :param key: Parameter name
        :param value: Parameter value
        """
        if key not in self.input_parameters:
            self.log_mssg(f"Unknown parameter: {key}", level="warning")
            return

        match key:
            case "Number of initial points" | "Number of total points" | "Number of Experiments per batch":
                if not isinstance(value, int) or value < 1:
                    self.log_mssg(f"{key} must be a positive integer, got {value}", level="warning")
                    return
            case "Acquisition Function":
                if value not in self.input_parameters[key]:
                    self.log_mssg(f"Unknown acquisition function: {value}", level="warning")
                    return
            case "Termination criterion":
                if value not in self.input_parameters[key]:
                    self.log_mssg(f"Unknown termination criterion: {value}", level="warning")
                    return
            case "Resubmission of Failed N":
                if not isinstance(value, int) or value < 0:
                    self.log_mssg(f"{key} must be a non-negative integer, got {value}", level="warning")
                    return

        self.parameters[key] = value
        self.log_mssg(f"Parameter {key} updated to {value}", level="ok")

    def _init_dragonfly(self):
        """
        Initialise the dragonfly EuclideanGPBandit optimiser in ask/tell mode.

        Creates the domain, function caller, and optimiser instances.
        The optimiser is configured with parameters from the frontend.
        """
        dim = self.bounds.shape[1]
        self.log_mssg(f"Initialising dragonfly with dim={dim}")

        # Create Euclidean domain in [0, 1]^d (normalised space)
        domain = EuclideanDomain([[0, 1]] * dim)

        # Create function caller (func=None for ask/tell mode)
        func_caller = EuclideanFunctionCaller(None, domain)

        # Build options with overrides
        all_args = get_all_euc_gp_bandit_args()
        partial_opts = {
            "acq": self.parameters.get("Acquisition Function", "ucb"),
            "num_init_evals": self.parameters.get("Number of initial points", 10),
            "mode": "asy",
        }
        options = load_options(all_args, partial_options=partial_opts)

        # Create optimiser in ask/tell mode
        self._optimiser = EuclideanGPBandit(
            func_caller, ask_tell_mode=True, options=options
        )
        self._optimiser.initialise()
        self._n_told = 0

        self.log_mssg(
            f"Dragonfly optimiser initialised: acq={options.acq}, "
            f"num_init={options.num_init_evals}",
            level="ok",
        )

    def first_run(self) -> pd.DataFrame:
        """
        Generate initial experimental points using dragonfly's built-in
        initialisation (Latin Hypercube / random sampling).

        :return: DataFrame with initial experimental points
        """
        self.log_mssg("Starting first run with dragonfly")
        self.run_index = 0

        n_initial = self.parameters["Number of initial points"]

        # Check if we already have some results
        if (
            hasattr(self, "results_df")
            and isinstance(self.results_df, pd.DataFrame)
            and not self.results_df.empty
        ):
            self.run_index = max(self.results_df["run_index"].values) + 1
            n_finished = len(self.results_df[self.results_df["status"] == "finished"])
            n_initial = max(0, n_initial - n_finished)

            if n_initial == 0:
                self.log_mssg(
                    "No initial points needed, returning existing results",
                    level="ok",
                )
                return self.results_df.copy()

        # Initialise dragonfly optimiser
        self._init_dragonfly()

        self.log_mssg(f"Requesting {n_initial} initial points from dragonfly")

        # Get initial points one at a time and submit each
        for i in range(n_initial):
            point = self._optimiser.ask()
            # Ensure point is a 1D array before converting to tensor
            point_array = np.atleast_1d(np.asarray(point, dtype=np.float64))
            tensor_point = torch.from_numpy(point_array)
            self.out_data(tensor_point)
            self.log_mssg(
                f"Initial point {i + 1}/{n_initial}: {point}, shape={tensor_point.shape}", level="ok"
            )

        self.log_mssg(f"All {n_initial} initial points submitted", level="ok")

    def update(self) -> None:
        """
        Core optimization loop:
        1. Process data from completed experiments
        2. Tell dragonfly the results
        3. Check termination criterion
        4. Ask dragonfly for the next point
        5. Submit the next experimental point
        """
        self.log_mssg("Starting dragonfly update loop")
        start_time = time.time()

        # 1. Process data
        x, y, y_var = self._process_data()

        if x.numel() == 0:
            self.log_mssg("No data available, signalling failures", level="warning")
            self.out_data("failures")
            return

        # 2. Tell dragonfly about newly completed results
        n_finished = len(self.results_df[self.results_df["status"] == "finished"])
        dim = self.bounds.shape[1]
        train_x = x.reshape(n_finished, -1)
        train_y = y.reshape(n_finished, -1)

        # Only tell about results that haven't been told yet
        n_new = n_finished - self._n_told
        if n_new > 0:
            tell_data = []
            for i in range(self._n_told, n_finished):
                point_list = train_x[i].tolist()
                value = float(train_y[i].item())
                tell_data.append((point_list, value))
            self._optimiser.tell(tell_data)
            self._n_told = n_finished
            self.log_mssg(
                f"Told dragonfly {n_new} new results", level="ok"
            )

        # 3. Check termination criterion
        if self.parameters.get("Termination criterion") == "max_iter":
            max_points = self.parameters.get("Number of total points", 0)
            if self.run_index >= max_points:
                self.log_mssg(
                    f"Reached max iterations ({self.run_index})", level="ok"
                )
                self.out_data("stop")
                return

        # 4. Ask dragonfly for the next point
        next_point = self._optimiser.ask()
        # Ensure next_point is a 1D array before converting to tensor
        next_point_array = np.atleast_1d(np.asarray(next_point, dtype=np.float64))
        candidate = torch.from_numpy(next_point_array)

        self.log_mssg(f"Dragonfly recommends: {next_point}, shape={candidate.shape}", level="ok")

        # 5. Submit the next point
        self.out_data(candidate)

        elapsed = time.time() - start_time
        self.log_mssg(f"Dragonfly update loop completed in {elapsed:.2f}s", level="ok")

    def _process_data(self) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        """
        Extract training tensors from results DataFrame.

        :return: Tuple of (x, y, y_var) tensors
        """
        self.log_mssg("Processing results into training tensors")
        x, y, y_var = self._from_df(self.results_df)
        self.log_mssg(
            f"Processed: x={x.shape}, y={y.shape}, "
            f"y_var={y_var.shape if y_var is not None else None}",
            level="ok",
        )
        return x, y, y_var
