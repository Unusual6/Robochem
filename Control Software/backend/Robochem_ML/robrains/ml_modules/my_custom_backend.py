"""
Custom ML Backend Template

This is a template for creating a custom ML algorithm.
Author: Your Name
"""

import time
from typing import Any, Optional, Tuple

import pandas as pd
import torch
from botorch import fit_gpytorch_mll
from botorch.acquisition import qLogExpectedImprovement
from botorch.models import SingleTaskGP
from botorch.models.transforms import Standardize
from botorch.optim import optimize_acqf
from botorch.utils import draw_sobol_samples
from gpytorch import ExactMarginalLogLikelihood

from robrains.communication_module import baseMLBackend
from robrains.utils import ColumnNormalizer


class MyCustomBackend(baseMLBackend):
    """
    Custom ML Backend Template
    
    This is a simple Bayesian Optimization backend template.
    You can modify this class to implement your own ML algorithm.
    
    Key methods to implement:
    - validate_and_update: Validate and update parameters from frontend
    - first_run: Generate initial experimental points
    - update: Core optimization loop (train model, propose next points)
    """

    # Define parameters that can be configured from the frontend
    input_parameters = {
        "Number of initial points": "int",
        "Number of total points": "int",
        "Number of Experiments per batch": "int",
        "Explorative Factor": "float",
        "Termination criterion": ["max_iter", "performance"],
        "Resubmission of Failed N": "int",
    }
    
    # Default values for the parameters
    input_defaults = {
        "Number of initial points": 10,
        "Number of total points": 100,
        "Number of Experiments per batch": 1,
        "Explorative Factor": 0.1,
        "Termination criterion": "max_iter",
        "Resubmission of Failed N": 0,
    }
    
    _bound_adjustment_method = "None"

    def __init__(self):
        super().__init__()

    def validate_and_update(self, key: str, value: Any) -> None:
        """
        Validate and update parameters from the frontend.
        
        :param key: Parameter name
        :param value: Parameter value
        """
        if key not in self.input_parameters:
            self.log_mssg(f"Unknown parameter: {key}", level="warning")
            return

        # Validate based on expected type
        match key:
            case "Number of initial points" | "Number of total points" | "Number of Experiments per batch":
                if not isinstance(value, int) or value < 1:
                    self.log_mssg(f"{key} must be a positive integer, got {value}", level="warning")
                    return
            case "Explorative Factor":
                if not isinstance(value, (int, float)) or value < 0:
                    self.log_mssg(f"{key} must be a non-negative number, got {value}", level="warning")
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

    def first_run(self) -> pd.DataFrame:
        """
        Generate initial experimental points using Sobol sampling.
        
        :return: DataFrame with initial experimental points
        """
        self.log_mssg("Starting first run")
        self.run_index = 0
        
        n_initial = self.parameters["Number of initial points"]
        
        # Check if we already have some results
        if hasattr(self, "results_df") and isinstance(self.results_df, pd.DataFrame) and not self.results_df.empty:
            self.run_index = max(self.results_df["run_index"].values) + 1
            n_finished = len(self.results_df[self.results_df["status"] == "finished"])
            n_initial = max(0, n_initial - n_finished)
            
            if n_initial == 0:
                self.log_mssg("No initial points needed, returning existing results", level="ok")
                return self.results_df.copy()
        
        self.log_mssg(f"Generating {n_initial} initial points")
        
        # Generate initial points using Sobol sampling
        bounds = self.bounds
        sobol_samples = draw_sobol_samples(bounds=bounds, n=n_initial, q=1).squeeze(1)
        
        # Submit the initial points
        self.log_mssg(f"Initial points generated, shape: {sobol_samples.shape}", level="ok")
        return self.out_data(sobol_samples)

    def update(self) -> None:
        """
        Core optimization loop:
        1. Process data from completed experiments
        2. Train surrogate model
        3. Optimize acquisition function to propose next point
        4. Submit next experimental point
        """
        self.log_mssg("Starting optimization loop")
        start_time = time.time()
        
        # 1. Process data
        x, y, y_var = self._process_data()
        
        if x.numel() == 0:
            self.log_mssg("No data available, signalling failures", level="warning")
            self.out_data("failures")
            return
        
        # 2. Check termination criterion
        if self.parameters.get("Termination criterion") == "max_iter":
            max_points = self.parameters.get("Number of total points", 0)
            if self.run_index >= max_points:
                self.log_mssg(f"Reached max iterations ({self.run_index})", level="ok")
                self.out_data("stop")
                return
        
        # 3. Normalize data
        n_finished = len(self.results_df[self.results_df["status"] == "finished"])
        train_x = x.reshape(n_finished, -1)
        train_y = y.reshape(n_finished, -1)
        
        self.normalizer = ColumnNormalizer(train_y)
        train_y_normalized = self.normalizer.normalize(train_y)
        
        self.log_mssg(f"Training data: x={train_x.shape}, y={train_y_normalized.shape}", level="ok")
        
        # 4. Train GP model
        model = SingleTaskGP(
            train_X=train_x,
            train_Y=train_y_normalized,
            covar_module=None,
            outcome_transform=Standardize(m=train_y_normalized.shape[-1]),
        )
        mll = ExactMarginalLogLikelihood(model.likelihood, model)
        fit_gpytorch_mll(mll)
        
        self.log_mssg("GP model trained", level="ok")
        
        # 5. Optimize acquisition function
        n_batch = self.parameters.get("Number of Experiments per batch", 1)
        bounds = self.bounds
        
        acqf = qLogExpectedImprovement(
            model=model,
            best_f=train_y_normalized.max(),
        )
        
        candidates, acq_value = optimize_acqf(
            acq_function=acqf,
            bounds=bounds,
            q=n_batch,
            num_restarts=10,
            raw_samples=512,
        )
        
        self.log_mssg(f"Next candidates: {candidates.shape}, acq={acq_value.item():.4f}", level="ok")
        
        # 6. Get predictions and submit
        with torch.no_grad():
            posterior = model.posterior(candidates)
            mean = posterior.mean
            variance = posterior.variance
            pred_y = self.normalizer.denormalize_mean_variance((mean, variance))
        
        self.out_data(candidates, predicted_y=pred_y)
        
        elapsed = time.time() - start_time
        self.log_mssg(f"Optimization loop completed in {elapsed:.2f}s", level="ok")

    def _process_data(self) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        """
        Extract training tensors from results DataFrame.
        
        :return: Tuple of (x, y, y_var) tensors
        """
        self.log_mssg("Processing results into training tensors")
        x, y, y_var = self._from_df(self.results_df)
        self.log_mssg(f"Processed: x={x.shape}, y={y.shape}, y_var={y_var.shape if y_var is not None else None}", level="ok")
        return x, y, y_var
