"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr:

"""

import numpy as np
import pandas as pd
import torch
from pyDOE import lhs
import random
from botorch.acquisition.objective import MCAcquisitionObjective
from gpytorch.kernels import (
    MaternKernel,
    ScaleKernel,
    IndexKernel,
    Kernel,
)
from typing import Union, Optional, List, Iterable, Sequence, Dict, Set, Tuple
import math
import functools


def initialise_parameter(
    parameters: Sequence,  # tuple | list of ML_parameter objects
    number_of_points: Optional[int] = None,
    method: str = "LHS",
    force_categorical: bool = False,
    *,
    existing_points: Union[
        None,
        pd.DataFrame,
        Sequence[torch.Tensor],
        torch.Tensor,
    ] = None,
    min_distance: float = 0.05,
    oversample_factor: int = 5,
) -> List[torch.Tensor]:
    """Generate **new** initialisation tensors, aware of points already evaluated.

    Parameters
    ----------
    parameters
        A sequence of *ML_parameter* objects.  Every object must expose at least
        one of the following translation attributes used by the legacy code:
        ``translation_continuous``, ``translation_discrete``, ``translation_task``,
        and optionally ``translation_fidelity``.
    number_of_points
        How many brand‑new points to output.  When *None*, the function falls
        back to ``max(10, 2*len(parameters), min_needed)``, where *min_needed* is
        the smallest number of points required to cover every categorical value
        *once* when ``force_categorical`` is *True*.
    method
        Either ``"LHS"`` or ``"Random"``.  Controls how the *continuous* part of
        candidate points is sampled.
    force_categorical
        When ``True`` the routine guarantees that **every** categorical value that
        has *not yet* appeared in *existing_points* will appear in the newly
        generated batch – possibly increasing ``number_of_points`` internally.
    existing_points
        Previously evaluated points.  Accepted formats:
        - **DataFrame** of *raw* values (column order must follow *parameters*).
        - **Tensor** or **list[Tensor]** already in the *encoded* space produced
          by an earlier call to this function.
    min_distance
        Minimum ℓ2 distance (computed in the 0‑1 continuous sub‑space) that each
        *new* point must keep from any *existing* point.
    oversample_factor
        How many *candidate* points to draw initially (``factor × number``) before
        whittling them down to the farthest‑apart subset.

    Returns
    -------
    list[torch.Tensor]
        Each tensor encodes one candidate in the exact concatenated order expected
        by the downstream optimiser.
    """

    # 1) Split parameters by kind ------------------------------------------------
    continuous_params, discrete_params, task_params = _split_parameters(parameters)

    # 2) Convert *existing* DataFrame / tensors into the analysis‑friendly form ----
    cont_seen, seen_categories, seen_tasks = _digest_existing_points(
        parameters,
        continuous_params,
        existing_points,
    )
    n_seen = cont_seen.shape[0]

    # 3) Decide how many fresh points are necessary ------------------------------
    number_of_points = _compute_point_budget(
        requested=number_of_points,
        discrete_params=discrete_params,
        force_categorical=force_categorical,
        n_features=len(parameters),
    )

    # 4) Continuous candidates ---------------------------------------------------
    continuous_values_dict = _sample_continuous_candidates(
        continuous_params,
        number_of_points,
        method,
        cont_seen,
        min_distance,
        oversample_factor,
    )

    # 5) Discrete + task candidates ---------------------------------------------
    discrete_values_dict = _sample_discrete_candidates(
        discrete_params,
        number_of_points,
        seen_categories,
        force_categorical,
    )

    task_values_dict = _sample_task_candidates(
        task_params,
        number_of_points,
        seen_tasks,
        force_categorical,
    )

    # 6) Assemble the final tensors ---------------------------------------------
    return _assemble_points(
        parameters,
        number_of_points,
        continuous_values_dict,
        discrete_values_dict,
        task_values_dict,
    )


# ---------------------------------------------------------------------------
# Helper functions (private) -------------------------------------------------
# ---------------------------------------------------------------------------


def _split_parameters(parameters: Sequence) -> Tuple[List, List, List]:
    """Split *parameters* into (continuous, discrete, task) lists."""
    continuous = [p for p in parameters if hasattr(p, "translation_continuous")]
    discrete = [p for p in parameters if hasattr(p, "translation_discrete")]
    task = [p for p in parameters if hasattr(p, "translation_task")]
    return continuous, discrete, task


def _digest_existing_points(
    parameters: Sequence,
    continuous_params: Sequence,
    existing: Union[None, pd.DataFrame, Sequence[torch.Tensor], torch.Tensor],
) -> Tuple[np.ndarray, Dict[str, Set], Dict[str, Set]]:
    """Normalise already‑evaluated points.

    Returns
    -------
    cont_seen : ndarray  (n_seen, n_cont)
        Continuous part mapped to the 0‑1 cube.
    seen_categories : dict[str, set]
        Raw categorical labels already encountered for each *discrete* parameter.
    seen_tasks : dict[str, set]
        Raw task labels already encountered for each *task* parameter.
    """
    seen_categories: Dict[str, Set] = {p.name: set() for p in parameters}
    seen_tasks: Dict[str, Set] = {p.name: set() for p in parameters}

    # shortcut – nothing to merge
    if existing is None:
        n_cont = len(continuous_params)
        return np.empty((0, n_cont)), seen_categories, seen_tasks

    # --- Case 1: DataFrame of raw values ------------------------------------
    if isinstance(existing, pd.DataFrame):
        cont_rows: List[List[float]] = []
        for _, row in existing.iterrows():
            cont_vals: List[float] = []
            for p in parameters:
                is_chem = getattr(p, "phy_chem", "Physical") == "Chemical"
                if hasattr(p, "translation_continuous"):
                    src = row[f"{p.name}_conc"] if is_chem else row[p.name]
                    enc = p.translation_continuous(src)
                    cont_vals.append(
                        float(enc.item())
                        if isinstance(enc, torch.Tensor)
                        else float(enc)
                    )
                if hasattr(p, "translation_discrete"):
                    seen_categories[p.name].add(row[p.name])
                if hasattr(p, "translation_task"):
                    seen_tasks[p.name].add(row[p.name])
            cont_rows.append(cont_vals)
        return np.asarray(cont_rows, dtype=float), seen_categories, seen_tasks

    # --- Case 2: Encoded tensors / list[tensor] ------------------------------
    if isinstance(existing, torch.Tensor):
        X = existing.clone().detach().double()
        if X.ndim == 1:
            X = X.unsqueeze(0)
    else:  # list / tuple of tensors
        X = torch.stack([pt.clone().detach().double() for pt in existing], 0)

    n_cont = len(continuous_params)
    cont_seen = X[:, :n_cont].numpy()

    # We cannot easily back‑translate encoded categoricals, but we can at least
    # record that *some* value has appeared so the later guarantee logic can
    # skip if necessary.
    disc_offset = n_cont
    for p_idx, p in enumerate(
        [pp for pp in parameters if hasattr(pp, "translation_discrete")]
    ):
        seen_categories[p.name] = {int(v.item()) for v in X[:, disc_offset + p_idx]}

    task_offset = n_cont + len(
        [pp for pp in parameters if hasattr(pp, "translation_discrete")]
    )
    for p_idx, p in enumerate(
        [pp for pp in parameters if hasattr(pp, "translation_task")]
    ):
        seen_tasks[p.name] = {int(v.item()) for v in X[:, task_offset + p_idx]}

    return cont_seen, seen_categories, seen_tasks


def _compute_point_budget(
    requested: Optional[int],
    discrete_params: Sequence,
    force_categorical: bool,
    n_features: int,
) -> int:
    """Decide how many *new* points we must create."""
    min_needed = (
        max((len(p.discrete) for p in discrete_params), default=0)
        if force_categorical
        else 0
    )
    if requested is None:
        return max(10, 2 * n_features, min_needed)
    return max(requested, min_needed)


def _sample_continuous_candidates(
    continuous_params: Sequence,
    n_points: int,
    method: str,
    cont_seen: np.ndarray,
    min_distance: float,
    oversample_factor: int,
) -> Dict[str, torch.Tensor]:
    """Create a dictionary `{param.name: tensor([size=n_points])}` for continuous dims."""
    n_cont = len(continuous_params)
    if n_cont == 0:
        return {}

    n_try = oversample_factor * n_points
    pool = (
        lhs(n_cont, samples=n_try)
        if method == "LHS"
        else np.random.uniform(0, 1, size=(n_try, n_cont))
    )

    # distance filter --------------------------------------------------------
    if cont_seen.size and cont_seen.shape[0]:
        dists = np.linalg.norm(pool[:, None, :] - cont_seen[None, :, :], axis=-1)
        pool = pool[dists.min(axis=1) >= min_distance]

    # replenish pool if we lost too many points ------------------------------
    while pool.shape[0] < n_points:
        extra = np.random.uniform(0, 1, size=(n_points, n_cont))
        if cont_seen.size and cont_seen.shape[0]:
            dists = np.linalg.norm(extra[:, None, :] - cont_seen[None, :, :], axis=-1)
            extra = extra[dists.min(axis=1) >= min_distance]
        pool = np.vstack([pool, extra])

    # greedy maximin pick ----------------------------------------------------
    chosen: List[np.ndarray] = []
    dist_to_set = (
        np.ones(pool.shape[0])
        if not cont_seen.size or not cont_seen.shape[0]
        else np.linalg.norm(pool[:, None, :] - cont_seen[None, :, :], axis=-1).min(
            axis=1
        )
    )
    for _ in range(n_points):
        idx = int(dist_to_set.argmax())
        chosen.append(pool[idx])
        new_pt = pool[idx : idx + 1]
        dist_to_set = np.minimum(dist_to_set, np.linalg.norm(pool - new_pt, axis=1))
        dist_to_set[idx] = -np.inf

    lhs_samples = np.vstack(chosen)
    return {
        p.name: torch.tensor(lhs_samples[:, i], dtype=torch.float64)
        for i, p in enumerate(continuous_params)
    }


def _sample_discrete_candidates(
    discrete_params: Sequence,
    n_points: int,
    seen_categories: Dict[str, Set],
    force_categorical: bool,
) -> Dict[str, List]:
    """Return dict `{param.name: list}` with length *n_points* for each discrete param."""
    out: Dict[str, List] = {}
    for p in discrete_params:
        unseen = [c for c in p.discrete if c not in seen_categories[p.name]]
        if n_points < len(unseen):
            if force_categorical:
                raise ValueError(
                    f"Need ≥{len(unseen)} points to cover unseen categories of '{p.name}'."
                )
            unseen = random.sample(unseen, k=n_points)
        samples = unseen + random.choices(p.discrete, k=n_points - len(unseen))
        random.shuffle(samples)
        out[p.name] = [p.translation_discrete(s) for s in samples]
    return out


def _sample_task_candidates(
    task_params: Sequence,
    n_points: int,
    seen_tasks: Dict[str, Set],
    force_categorical: bool,
) -> Dict[str, torch.Tensor]:
    """Return dict `{param.name: tensor}` for task parameters."""
    out: Dict[str, torch.Tensor] = {}
    for p in task_params:
        if getattr(p, "task_value", None) is not None:
            out[p.name] = torch.tensor(
                [p.translation_task(p.task_value)] * n_points, dtype=torch.int64
            )
            continue

        unseen = [c for c in p.discrete if c not in seen_tasks[p.name]]
        if n_points < len(unseen):
            if force_categorical:
                raise ValueError(
                    f"Need ≥{len(unseen)} points for unseen task categories of '{p.name}'."
                )
            unseen = random.sample(unseen, k=n_points)
        samples = unseen + random.choices(p.discrete, k=n_points - len(unseen))
        random.shuffle(samples)
        out[p.name] = torch.tensor(
            [p.translation_task(s) for s in samples], dtype=torch.int64
        )
    return out


def _assemble_points(
    parameters: Sequence,
    n_points: int,
    cont_vals: Dict[str, torch.Tensor],
    disc_vals: Dict[str, List],
    task_vals: Dict[str, torch.Tensor],
) -> List[torch.Tensor]:
    """Concatenate per‑parameter pieces into the final list of tensors."""
    points: List[torch.Tensor] = []
    for i in range(n_points):
        parts: List[torch.Tensor] = []
        for p in parameters:
            if hasattr(p, "translation_continuous"):
                parts.append(cont_vals[p.name][i].unsqueeze(0))
            if hasattr(p, "translation_discrete"):
                v = disc_vals[p.name][i]
                parts.append(
                    v.view(-1)
                    if isinstance(v, torch.Tensor)
                    else torch.tensor(v).unsqueeze(0)
                )
            if hasattr(p, "translation_fidelity"):
                parts.append(torch.tensor([1.0], dtype=torch.float64))
            if hasattr(p, "translation_task"):
                parts.append(task_vals[p.name][i].unsqueeze(0))
        points.append(torch.cat(parts))
    return points


class MainTaskObjective(MCAcquisitionObjective):
    def __init__(self, task_index: int):
        """posterior transform to focus on optimising main task only"""
        super().__init__()
        self.task_index = task_index

    def forward(self, samples, **kwargs):
        print(samples[..., self.task_index].shape)
        return samples[..., self.task_index]


class Kernelizer(Kernel):
    """Botorch is being a bit of a woozy bitch and doesn't like my one hot encoded data. So we
    need a kernel method that allows us to get some covariance matrices that make sense for a mixed input

    """

    def __init__(
        self,
        continuous_indices: list,
        categorical_indices: list,
        categorical_levels: list,
        special_feature: int | None = None,
    ):
        """
        initialises the kernel as a matern kernel for the continuous indexes and a index kernel for the categoricals
        given the tensor X of length m which has some categoricals of level x and some continuous values.
        param: continuous_indexes, list of indexes in the tensor which are active dimensions for the continuous parameters
        param: categorical_indexes, list of indexes in the tensor which are categorical features.
        param: categorical_levels, list of number of levels for each categorical index
        param: special_feature, position of the task or fidelity feature. we use this to modify the indexes as the
        multifidelity and multitask models will remove the task feature from the input tensor
        """
        super(Kernelizer, self).__init__()
        self.continuous_indices = continuous_indices
        self.categorical_indices = categorical_indices
        self.categorical_levels = categorical_levels
        self.special_feature = special_feature
        if self.special_feature is not None:
            self.magic_indexing()

        self.continuous_kernel = ScaleKernel(
            MaternKernel(ard_num_dims=len(self.continuous_indices))
        )
        self.categorical_kernels = []
        for i, levels in enumerate(categorical_levels):
            self.categorical_kernels.append(
                IndexKernel(num_tasks=levels, rank=levels - 1)
            )

    def magic_indexing(self):
        """goes through the continuous and categorical indices and modifies them to account for the special feature
        the idea is that if the index is less than the special feature we don't need to modify it, if it is greater
        we need to subtract one from the index
        """
        for i, index in enumerate(self.continuous_indices):
            if index > self.special_feature:
                self.continuous_indices[i] -= 1
        for i, index in enumerate(self.categorical_indices):
            if index > self.special_feature:
                self.categorical_indices

    def forward(self, X1, X2, **params):
        # Print shapes for debugging
        # print(f"Shapes: X1 = {X1.shape}, X2 = {X2.shape}, params = {params}")

        # Partition the input tensors into continuous and categorical parts
        continuous_X1, continuous_X2 = (
            X1[..., self.continuous_indices],
            X2[..., self.continuous_indices],
        )
        categorical_X1, categorical_X2 = (
            X1[..., self.categorical_indices],
            X2[..., self.categorical_indices],
        )

        # Apply the continuous kernel to the continuous parts of the input
        continuous_covar = self.continuous_kernel(
            continuous_X1, continuous_X2, **params
        )

        # Apply the categorical kernels to the categorical parts
        categorical_covar = None
        for i, cat_kernel in enumerate(self.categorical_kernels):
            # Check if the shapes of X1 and X2 are different, and only broadcast if needed
            if categorical_X1.shape != categorical_X2.shape:
                # Perform broadcasting for the categorical values
                cat_X1_broadcasted = categorical_X1[..., i].unsqueeze(
                    -1
                )  # Add a singleton dimension for broadcasting
                cat_X2_broadcasted = categorical_X2[..., i].unsqueeze(
                    -1
                )  # Add a singleton dimension for broadcasting
            else:
                # No need to broadcast if the shapes are already aligned
                cat_X1_broadcasted = categorical_X1[..., i]
                cat_X2_broadcasted = categorical_X2[..., i]

            # Now apply the categorical kernel across the (possibly broadcasted) tensors
            cat_covar = cat_kernel(
                cat_X1_broadcasted.long(), cat_X2_broadcasted.long(), **params
            )

            if categorical_covar is None:
                categorical_covar = cat_covar
            else:
                categorical_covar = categorical_covar + cat_covar

        # Sum the continuous and categorical covariance matrices
        return continuous_covar + categorical_covar


class FloatWithError:
    """
    A class to represent a float value with its associated error.
    Supports basic arithmetic operations with error propagation.
    Handles NaN values for value or error gracefully.
    """

    def __init__(
        self, value: Optional[float] = None, error: Optional[float] = None
    ) -> None:
        """
        Initialize a FloatWithError object.

        :param value: The central value of the float (can be NaN).
        :param error: The associated error of the float (can be NaN). variance passed so +- needs to be the sqrt
        """
        self.value: float = value if value is not None else float("nan")
        self.error: float = np.sqrt(error) if error is not None else float("nan")

    @staticmethod
    def _format_number(number: float) -> str:
        """
        formats the number, to "NaN" if the number is not a number otherwise:
        to fixed point notation or scientigic notation
        """
        if math.isnan(number):
            return "NaN"
        elif abs(number) < 1000 and abs(number) >= 0.001:
            return f"{number:.4g}"
        else:
            return f"{number:.4e}"

    def __repr__(self) -> str:
        """
        Return a string representation of the object in the format "value ± error".

        :return: A string representation of the FloatWithError object.
        """
        value_repr = self._format_number(self.value)
        error_repr = self._format_number(self.error)
        return f"{value_repr} ± {error_repr}"

    def _effective_error(self, error: float) -> float:
        """
        Treat NaN errors as 0 for calculations.

        :param error: The error value to evaluate.
        :return: The effective error (NaN treated as 0).
        """
        return 0.0 if math.isnan(error) else error

    def __add__(self, other: Union[float, int, "FloatWithError"]) -> "FloatWithError":
        """
        Add another float or FloatWithError to this object, propagating errors.

        :param other: The other operand, either a float or a FloatWithError.
        :return: A new FloatWithError representing the sum.
        """
        if isinstance(other, FloatWithError):
            value = (self.value if not math.isnan(self.value) else 0) + (
                other.value if not math.isnan(other.value) else 0
            )
            error = (
                self._effective_error(self.error) ** 2
                + self._effective_error(other.error) ** 2
            ) ** 0.5
            return FloatWithError(value, error)
        elif isinstance(other, (float, int)):
            value = (self.value if not math.isnan(self.value) else 0) + other
            return FloatWithError(value, self._effective_error(self.error))
        else:
            return NotImplemented

    def __sub__(self, other: Union[float, int, "FloatWithError"]) -> "FloatWithError":
        """
        Subtract another float or FloatWithError from this object, propagating errors.

        :param other: The other operand, either a float or a FloatWithError.
        :return: A new FloatWithError representing the difference.
        """
        if isinstance(other, FloatWithError):
            value = (self.value if not math.isnan(self.value) else 0) - (
                other.value if not math.isnan(other.value) else 0
            )
            error = (
                self._effective_error(self.error) ** 2
                + self._effective_error(other.error) ** 2
            ) ** 0.5
            return FloatWithError(value, error)
        elif isinstance(other, (float, int)):
            value = (self.value if not math.isnan(self.value) else 0) - other
            return FloatWithError(value, self._effective_error(self.error))
        else:
            return NotImplemented

    def __mul__(self, other: Union[float, int, "FloatWithError"]) -> "FloatWithError":
        """
        Multiply this object by another float or FloatWithError, propagating errors.

        :param other: The other operand, either a float or a FloatWithError.
        :return: A new FloatWithError representing the product.
        """
        if isinstance(other, FloatWithError):
            value = (self.value if not math.isnan(self.value) else 1) * (
                other.value if not math.isnan(other.value) else 1
            )
            error = (
                abs(value)
                * (
                    (
                        self._effective_error(self.error) / self.value
                        if self.value != 0
                        else 0
                    )
                    ** 2
                    + (
                        self._effective_error(other.error) / other.value
                        if other.value != 0
                        else 0
                    )
                    ** 2
                )
                ** 0.5
            )
            return FloatWithError(value, error)
        elif isinstance(other, (float, int)):
            value = (self.value if not math.isnan(self.value) else 1) * other
            return FloatWithError(value, abs(other) * self._effective_error(self.error))
        else:
            return NotImplemented

    def __truediv__(
        self, other: Union[float, int, "FloatWithError"]
    ) -> "FloatWithError":
        """
        Divide this object by another float or FloatWithError, propagating errors.

        :param other: The other operand, either a float or a FloatWithError.
        :return: A new FloatWithError representing the quotient.
        """
        if isinstance(other, FloatWithError):
            value = (self.value if not math.isnan(self.value) else 1) / (
                other.value if not math.isnan(other.value) else 1
            )
            error = (
                abs(value)
                * (
                    (
                        self._effective_error(self.error) / self.value
                        if self.value != 0
                        else 0
                    )
                    ** 2
                    + (
                        self._effective_error(other.error) / other.value
                        if other.value != 0
                        else 0
                    )
                    ** 2
                )
                ** 0.5
            )
            return FloatWithError(value, error)
        elif isinstance(other, (float, int)):
            value = (self.value if not math.isnan(self.value) else 1) / other
            return FloatWithError(value, abs(self._effective_error(self.error) / other))
        else:
            return NotImplemented


class ColumnNormalizer:
    def __init__(self, tensor: torch.Tensor):
        """
        Initialize the ColumnNormalizer with a tensor.
        Computes and stores the min and max values for each column.
        """
        self.min_vals = tensor.min(dim=0, keepdim=True)[
            0
        ]  # Minimum value for each column
        self.max_vals = tensor.max(dim=0, keepdim=True)[
            0
        ]  # Maximum value for each column
        self.ranges = self.max_vals - self.min_vals  # Range for each column
        self.ranges[self.ranges == 0] = 1  # Avoid division by zero

    def normalize(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Normalize the input tensor column-wise to the range [0, 1].
        """
        return (tensor - self.min_vals) / self.ranges

    def normalize_variance(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Normalize the input tensor column-wise to the same range as the Y
        """
        return tensor / self.ranges**2

    def denormalize(self, normalized_tensor: torch.Tensor) -> torch.Tensor:
        """
        Transform a tensor in the range [0, 1] back to the original tensor range.
        """
        return normalized_tensor * self.ranges + self.min_vals

    def denormalize_mean_variance(self, mean_variance: tuple) -> tuple:
        """
        Denormalize the mean and variance of a normalized tensor back to the original tensor range.

        Args:
            mean_variance (tuple): A tuple containing:
                - mean: Tensor of shape (m, n) representing the mean of the normalized tensor.
                - variance: Tensor of shape (m, n) representing the variance of the normalized tensor.

        Returns:
            tuple: A tuple containing:
                - denormalized_mean: Tensor of shape (m, n) representing the mean in the original range.
                - denormalized_variance: Tensor of shape (m, n) representing the variance in the original range.
        """
        mean, variance = mean_variance

        # Denormalize the mean
        denormalized_mean = mean * self.ranges + self.min_vals

        # Denormalize the variance
        # Variance scales quadratically with the range (because variance is related to squared differences)
        denormalized_variance = variance**0.5 * self.ranges

        return denormalized_mean, denormalized_variance
