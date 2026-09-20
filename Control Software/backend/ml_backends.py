"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr:

"""

import copy
import time
from typing import List, Optional, Union

import numpy as np
import pandas as pd
import torch

from omniplatypus.procedures.analytics.analytics_parameters import AnalyticalParameter
from omniplatypus.procedures.experiments.base_experiment import (
    NumericalParameter,
    ExperimentalParameter,
    ChemicalParameter,
    RunResult,
)
from robrains.communication_module import (
    ML_Platform_HITL,
    ML_Platform_HITL_Development,
    ML_Platform,
)
from robrains.ml_modules import (
    SingleBayesianOptiBackend,
    EfficientBatchedBOBackend,
    AllScopeTaskBackend,
    DevelopmentHITL,
    ScopeAcceleratorTaskBackend,
    EnantioExtravaganzaBackend,
    MyCustomBackend,
    DragonflyBackend,
)
from robrains.parameter_backends import (
    Chemical,
    AnalyParameter,
    PhysicalParameter,
    ExpParameter,
)


class ToandFromMachine:
    """Before these two methods were defined in the RobochemML package. but realistically these are specific for the OmniPlatypus
    robochem. So they are moved here where OmniPlatypus is available"""

    # Higher numbers correspond to higher priority in the sampling process.
    # limiting reagents (on which yields are calculated) is expected to have highest priority.
    _sampling_priorities = {
        "Limiting Reagent": 50000,
        "Excess Reagent": 30000,
        "Sacrificial Reagent": 20000,
        "Other Reagent": 40000,
        "Other Reagent II": 3900,
        "Catalyst": 10000,
        "Co-catalyst": 9000,
        "Ligand": 8000,
        "Buchwald Ligand": 8000,
        "Additive": 7000,
        "Additive II": 6900,
        "Additive III": 6800,
        "Jerry": 6700,
        "Jerry II": 6600,
        "Solvent": 1000,
        "Solvent II": 1000,
        "Co-Solvent": 500,
        "Constant": 3800,
        "Technique": 3700,
    }

    def _to_machine(self, tensor: torch.tensor):
        """takes the values from the ml environment and translates it to the recipe for the hardware environment:

        the tensor is translated into a list of chemical and physical parameters of type NumericalParameter and ExperimentalParameter
        example chemical:
        ExperimentalParameter(name = "Chemical_name", value = 0.5 (concentration), unit = 'mM')
        Experimental_parameter.foreign_key = "Ml_parameter_name"

        for physical:
        NumericalParameter(name = "Physical_name", value = 0.5, unit = 'mM')
        NumericalParameter.foreign_key = "Ml_parameter_name"

        also add all the constants to the list of parameters,

        param tensor: torch.tensor, tensor of the values to translate
        returns: list, list of tuples with the translated values
        """
        # for each parameter in the ML_parameters, translate the values
        if self._hitl_tag == False:
            target_c = [
                mach
                for mach in self.constants
                if mach.name == "yield_calculation_chemical"
            ]
            if len(target_c) > 0:
                target_chemical = target_c[0]

        translated_values = []
        target_chemical_value = None
        for parameter in self.ML_parameters:
            param_name = parameter.name
            phy_chem = "Chemical" if parameter.phy_chem == "Chemical" else "Physical"
            value_continuous = None
            value_discrete = None

            if f"{param_name}_continuous" in self.check_dict:
                tensor_continuous_value = tensor[
                    self.check_dict[f"{param_name}_continuous"]
                ]
                value_continuous = parameter.back_translation_continuous(
                    tensor_continuous_value.item()
                )
            elif parameter.constant_valued == True:
                value_continuous = parameter.const_value

            if f"{param_name}_discrete" in self.check_dict:
                index = self.check_dict[f"{param_name}_discrete"]
                if isinstance(index, int):
                    tensor_discrete_value = tensor[index]
                    value_discrete = parameter.back_translation_discrete(
                        tensor_discrete_value.item()
                    )
                else:
                    tensor_discrete_value = tensor[index[0] : index[1]]
                    value_discrete = parameter.back_translation_discrete(
                        tensor_discrete_value
                    )
            elif f"{param_name}_task" in self.check_dict:
                index = self.check_dict[f"{param_name}_task"]
                tensor_discrete_value = tensor[index]
                value_discrete = parameter.back_translation_task(
                    tensor_discrete_value.item()
                )
            elif f"{param_name}_fidelity" in self.check_dict:
                index = self.check_dict[f"{param_name}_fidelity"]
                tensor_discrete_value = tensor[index]
                value_discrete = parameter.back_translation_fidelity(
                    tensor_discrete_value.item()
                )

            elif parameter.discrete_single_value:
                value_discrete = parameter.discrete[0]

            if phy_chem == "Chemical":
                to_append = ChemicalParameter(
                    name=value_discrete,
                    value=value_continuous,
                    units=parameter.unit,
                )
                to_append.foreign_key = param_name
                sampling_priority = self._sampling_priorities.get(parameter.name, None)
                if sampling_priority is not None:
                    to_append.sampling_priority = sampling_priority
            elif value_discrete is not None:
                # check the type of the value:
                if isinstance(value_discrete, str):
                    to_append = ExperimentalParameter(
                        name=param_name, value=value_discrete
                    )
                    to_append.foreign_key = param_name
                elif isinstance(value_discrete, float) or isinstance(
                    value_discrete, int
                ):
                    to_append = NumericalParameter(
                        name=param_name,
                        value=value_continuous,
                        units=parameter.unit,
                    )
                    to_append.foreign_key = param_name
            elif value_continuous is not None:
                to_append = NumericalParameter(
                    name=param_name, value=value_continuous, units=parameter.unit
                )
                to_append.foreign_key = param_name
            else:
                raise ValueError("No value found for the parameter")
            if "target_chemical" in locals() and target_chemical.value == param_name:
                target_chemical_value = value_discrete
            translated_values.append(to_append)

        # find all the constants and add them to the list:
        for constant in self.constants:
            if constant.name == "yield_calculation_chemical":
                if target_chemical_value is None:
                    raise ValueError(
                        f"Did not find the chemical to calculate yield for ('{target_chemical.value}')."
                    )

                to_append = AnalyticalParameter(
                    name=constant.name, value=target_chemical_value, units=""
                )
                translated_values.append(to_append)
                continue

            elif isinstance(constant, AnalyParameter):
                if constant.name in ["target_peak", "retention_time"] and isinstance(
                    constant.value, pd.DataFrame
                ):
                    if target_chemical_value in constant.value["Chemical"].values:
                        # Select the correct column dynamically
                        column_name = (
                            "peak_position(ppm)"
                            if constant.name == "target_peak"
                            else "Retention Time (min)"
                        )
                        value = constant.value.loc[
                            constant.value["Chemical"] == target_chemical_value,
                            column_name,
                        ].values[0]
                    else:
                        raise ValueError(
                            f"Chemical '{target_chemical_value}' not found in {constant.name} data."
                        )
                    min_value = None
                    max_value = None

                else:
                    min_value = constant.min_value
                    max_value = constant.max_value
                    value = constant.value

                # Ensure value is a float
                to_append = AnalyticalParameter(
                    name=constant.name,
                    value=value,
                    min_value=min_value,
                    max_value=max_value,
                    units=constant.unit,
                    tag=constant.omni_tag,
                )

            elif isinstance(constant, Chemical):
                to_append = ChemicalParameter(
                    name=constant.name, value=constant.value, units=constant.unit
                )
                sampling_priority = self._sampling_priorities.get(
                    constant.purpose, None
                )
                if sampling_priority is not None:
                    to_append.sampling_priority = sampling_priority
            elif isinstance(constant, PhysicalParameter):
                to_append = NumericalParameter(
                    name=constant.name, value=constant.value, units=constant.unit
                )
            elif isinstance(constant, ExpParameter):
                to_append = ExperimentalParameter(
                    name=constant.name,
                    value=constant.value,
                    allowed_values=constant.allowed_values,
                )
            to_append.foreign_key = constant.name
            translated_values.append(to_append)

        for machine in self.parameter_machine:
            match machine.name:
                case "sample_name":
                    to_append = copy.deepcopy(machine)
                    name = f'run{self.run_index}_{time.strftime("%Y%m%d%H%M%S", time.localtime())}'
                    to_append.value = to_append.value(name)
                    self._add_savename_to_df(
                        savename=to_append.value, run_index=self.run_index
                    )
                case _:
                    to_append = copy.deepcopy(machine)

            translated_values.append(to_append)

        self._update_utilities_df(recipe=translated_values, out_in="in")

        return translated_values

    def _from_machine(self, results: RunResult):
        """takes the values from the hardware environment and translates it to the torch tensor for the ML environment:

        which arrive in the form of a RunResult object.

        and transforms them back into a x and y tensors for the ml environment

        results: RunResult, the results from the hardware environment

        returns run_index, x, y
        """

        self.log_mssg(message=f"Received Run result: {results}", level="ok")
        run_index = results.run_id
        targets = results.result
        success = results.success
        recipe = results.parameters
        self._update_utilities_df(recipe=recipe, run_index=run_index, out_in="out")

        vial_idx = (
            results.collection_vial_id
            if results.collection_vial_id
            else "Not Collected"
        )
        save_file_name = [param for param in recipe if param.name == "sample_name"]
        if len(save_file_name) > 0:
            save_file_name = save_file_name[0].value
        else:
            save_file_name = None

        if not success:
            return run_index, None, None, None, vial_idx, None

        y = torch.zeros(len(self.targets), dtype=torch.float64)
        y_var = torch.zeros(len(self.targets), dtype=torch.float64)
        # turn the results into a tensor
        if targets != None:
            # now we know the targets should be a dictionary target name: value
            metrics = self.calculate_metrics(targets=targets, recipe=recipe)
            for ind, tar in enumerate(self.targets):
                y[ind] = metrics[tar]
                y_var[ind] = metrics.get(f"{tar}_variance", 0.0)

        param_names = {param.name: param for param in self.ML_parameters}
        # make an empty tensor of zeroes to fill in the values
        tensor_x = torch.zeros(self.tensor_shape[-1], dtype=torch.float64)
        for parameter in recipe:
            # loop through all the parameters in the recipe
            # if the parameter foreign key is not in the ML parameters, it's a constant, skip it
            if (
                not hasattr(parameter, "foreign_key")
                or parameter.foreign_key not in param_names.keys()
            ):
                continue

            param_name = parameter.foreign_key
            ml_parameter = param_names[param_name]
            phy_chem = "Chemical" if ml_parameter.phy_chem == "Chemical" else "Physical"
            value_continuous = None
            value_discrete = None

            if phy_chem == "Chemical":
                # Handle chemical parameters
                if ml_parameter.constant_valued == False:
                    value_continuous = ml_parameter.translation_continuous(
                        parameter.value
                    )
                if ml_parameter.task_feature == True:
                    value_discrete = ml_parameter.translation_task(parameter.name)
                elif ml_parameter.fidelity_feature == True:
                    value_discrete = ml_parameter.translation_fidelity(parameter.name)
                elif ml_parameter.discrete_single_value == False:
                    value_discrete = ml_parameter.translation_discrete(parameter.name)

            elif phy_chem == "Physical":
                # Handle physical parameters
                if hasattr(ml_parameter, "translation_continuous"):
                    value_continuous = ml_parameter.translation_continuous(
                        parameter.value
                    )
                elif hasattr(parameter, "translation_discrete"):
                    value_discrete = ml_parameter.translation_discrete(parameter.value)

            if value_continuous is not None:
                position_value_continuous = self.check_dict[f"{param_name}_continuous"]
                tensor_x[position_value_continuous] = value_continuous
            if value_discrete is not None:
                if f"{param_name}_task" in self.check_dict:
                    position_value_discrete = self.check_dict[f"{param_name}_task"]
                elif f"{param_name}_fidelity" in self.check_dict:
                    position_value_discrete = self.check_dict[f"{param_name}_fidelity"]
                elif (
                    isinstance(self.check_dict[f"{param_name}_discrete"], int)
                    or isinstance(self.check_dict[f"{param_name}_discrete"], list)
                    or isinstance(self.check_dict[f"{param_name}_discrete"], tuple)
                ):
                    position_value_discrete = self.check_dict[f"{param_name}_discrete"]
                else:
                    self.log_mssg(
                        f"Discrete parameter: {param_name} missing from check dict",
                        level="error",
                    )
                    raise ValueError(
                        f"Poorly defined discrete parameter: {param_name} missing from check dict"
                    )

                if isinstance(position_value_discrete, int):
                    tensor_x[position_value_discrete] = value_discrete
                else:
                    tensor_x[
                        position_value_discrete[0] : position_value_discrete[1]
                    ] = value_discrete

        # x = torch.tensor(tensor_x, dtype=torch.float64)
        x = tensor_x.clone().detach()
        return run_index, x, y, y_var, vial_idx, save_file_name

    def _update_utilities_df(
        self,
        recipe: List[ExperimentalParameter],
        run_index: Optional[int] = None,
        out_in: str = "in",
    ) -> None:
        """
        Update the utilities DataFrame with input or output parameters for tracking.

        Each run (identified by run_index) gets its own row; columns are named like
        "paramName_in(unit)" or "paramName_out(unit)" and are created on demand.
        Existing data for other parameters or runs is preserved.

        Args:
            recipe (List[ExperimentalParameter]): Parameters to record.
            run_index (Optional[int]): Identifier for this run. Defaults to self.run_index.
            out_in (str): Either "in" or "out" to suffix the column names.
        """
        # Ensure the DataFrame exists
        if not hasattr(self, "utilities_df"):
            self.utilities_df = pd.DataFrame()

        # Determine which run we're tracking
        if run_index is None:
            run_index = self.run_index

        # Build the data for this row
        row_data: dict[str, Union[int, float, str]] = {"run_index": run_index}
        for param in recipe:
            # Safe-get unit, default to empty string
            unit_str = f" [{param.unit}]" if getattr(param, "unit", None) else ""
            col = f"{param.name}_{out_in}{unit_str}"
            value = param.value
            if value == "":
                value = None
            try:
                val_temp = float(value)
                value = val_temp
            except Exception as e:
                pass

            row_data[col] = value

        # Use .loc to insert/update — this will add any new columns automatically
        self.utilities_df.loc[run_index, list(row_data.keys())] = list(
            row_data.values()
        )

    def calculate_metrics(self, targets: dict = None, recipe: list = None):
        """
        Calculate various metrics based on the provided targets and recipe.
        """
        if targets is None:
            targets = {}
        if recipe is None:
            recipe = []

        metrics = {}
        yield_value = targets.get("yield", 0)
        yield_variance = targets.get("yield_variance", 0.0)
        conversion = targets.get("conversion", 0)
        conversion_variance = targets.get("conversion_variance", 0)
        yield_sideproduct_a = targets.get("yield_sideproduct_A", 0)
        yield_sideproduct_b = targets.get("yield_sideproduct_B", 0)
        conversion_sideproduct_a = targets.get("conversion_sideproduct_A", 0)
        conversion_sideproduct_b = targets.get("conversion_sideproduct_B", 0)

        for target in self.targets:
            match target:
                case "yield":
                    metrics[target] = yield_value
                    metrics[f"{target}_variance"] = yield_variance
                case "conversion":
                    # metrics[target] = conversion
                    # metrics[f"{target}_variance"] = conversion_variance
                    metrics[target] = conversion_sideproduct_a
                case "cost":
                    metrics[target] = self._calculate_cost(recipe)
                case "throughput":
                    metrics[target] = self._calculate_throughput(recipe, yield_value)
                case "selectivity":
                    metrics[target] = self._calculate_selectivity(
                        yield_value, yield_sideproduct_a, yield_sideproduct_b
                    )
                case "residence_time":
                    metrics[target] = self._get_recipe_value(recipe, "residence_time")[
                        0
                    ]
                case "light_power_efficiency":
                    metrics[target] = self._calculate_light_power_efficiency(
                        recipe, yield_value
                    )
                case "light_power":
                    metrics[target] = self._get_recipe_value(recipe, "light_intensity")[
                        0
                    ]
                case "cost_per_unit_product":
                    metrics[target] = self._calculate_cost_per_unit_product(
                        recipe, yield_value
                    )
                case "mass_balance":
                    metrics[target] = self._calculate_mass_balance(recipe)
                case "Elia-metric":
                    metrics[target] = self._calculate_Elia_metric(recipe)
                case "integral_product":
                    metrics[target] = targets.get("integral", 0.0)
                case "integral_sideproduct":
                    int_1 = targets.get("integral_sideproduct_A", 0.0)
                    int_2 = targets.get("integral_sideproduct_B", 0.0)
                    int_1 = int_1 if int_1 > 0.0 else 0.0
                    int_2 = int_2 if int_2 > 0.0 else 0.0
                    metrics[target] = -1.0 * (int_1 + int_2)
                case "integral_starting_material":
                    metrics[target] = targets.get("integral_starting_material", 0.0)
                case "concetration_starting_material":
                    metrics[target] = targets.get(
                        "concentration_starting_material", 0.0
                    )
                    metrics[f"{target}_variance"] = targets.get(
                        "concentration_starting_material_variance", 0.0
                    )
                case "concetration_product":
                    metrics[target] = targets.get("concentration_product", 0.0)
                    metrics[f"{target}_variance"] = targets.get(
                        "concentration_product_variance", 0.0
                    )
                case "enantiomeric excess":
                    metrics[target] = self._calculate_ee(targets)

                case "diastereomeric ratio":
                    metrics[target] = self._calculate_dr(targets)

                case "total integral chirals":
                    metrics[target] = self._calculate_total_chirals(targets)

                case _:
                    raise ValueError(
                        "Simone is annoyed at you for not putting down the rigth target! Go in your room and think about what you have done!"
                    )

        return metrics

    def _calculate_ee(self, targets: dict):
        """calculates the enantiomeric excess

        given that integral is the integral of the product of interest and sideproduct A is it's enantiomer

        param targets: the targets returned from the analyis

        returns: float
        """
        integral_prod = targets.get("integral", 0.0)
        integral_enantiomer = targets.get("integral_sideproduct_A", 0.0)

        sum_int = integral_prod + integral_enantiomer

        try:
            value = (integral_prod - integral_enantiomer) / sum_int
        except ZeroDivisionError as e:
            value = 0.0

        return value * 100.0

    def _calculate_dr(self, targets: dict):
        """calculates the diastereomeric ratio

        given that your product of interest is the product, it's enantiomer sideproduct_A and the diastereomers
        Sideproduct _B and C

        param targets: the targets returned from the analyis

        returns: float
        """
        int_product = targets.get("integral", 0.0)
        int_enant = targets.get("integral_sideproduct_A", 0.0)
        int_dia1 = targets.get("integral_sideproduct_B", 0.0)
        int_dia2 = targets.get("integral_sideproduct_C", 0.0)

        try:
            value = (int_product + int_enant) / (int_dia1 + int_dia2)
        except ZeroDivisionError as e:
            value = 100.0

        if value > 100.0:
            value = 100.0

        if value < 0.01:
            value = 0.01

        return value

    def _calculate_total_chirals(self, targets: dict):
        """
        Calculates the total integral of the chiral componetns (to then be recalibrated to yield,
        these are linearly dependend)

        given that your product of interest is the product, it's enantiomer sideproduct_A and the diastereomers
        Sideproduct _B and C

        param targets: dict, target of results from analysis

        returns float
        """
        int_product = targets.get("integral", 0.0)
        int_enant = targets.get("integral_sideproduct_A", 0.0)
        int_dia1 = targets.get("integral_sideproduct_B", 0.0)
        int_dia2 = targets.get("integral_sideproduct_C", 0.0)

        value = int_product + int_enant + int_dia1 + int_dia2

        return value

    def _get_recipe_value(self, recipe, param_name, default_value=0):
        """
        Retrieve the value and units of a parameter from the recipe.
        """
        for param in recipe:
            if param.name == param_name:
                return param.value, getattr(param, "units", None)
        return default_value, None

    def _get_limiting_reagents(self):
        """
        Extract and flatten the list of limiting reagents.
        """
        for param in self.ML_parameters:
            if param.name == "Limiting Reagent":
                return [item for sublist in param.discrete for item in sublist]
        return []

    def _calculate_cost(self, recipe):
        """
        Calculate the total cost based on the cost per unit mass for each chemical in the recipe.
        """
        dict_of_costs = {}
        for param in self.ML_parameters:
            if hasattr(param, "prices") and isinstance(param.prices, dict):
                dict_of_costs.update(param.prices)
        limiting_reagents = self._get_limiting_reagents()
        slug_size, _ = self._get_recipe_value(recipe, "slug_size", 500.0)
        slug_volume_l = slug_size * 1e-6  # Convert microliters to liters

        total_cost = 0
        limiting_reagent_concentration = 0

        # Calculate cost for the limiting reagent
        for param in recipe:
            if param.name in limiting_reagents:
                limiting_reagent_concentration = param.value
                total_cost += (
                    dict_of_costs.get(param.name, 0)
                    * limiting_reagent_concentration
                    * slug_volume_l
                )
                break

        # Calculate cost for other reagents
        for param in recipe:
            if param.name not in limiting_reagents and param.name in dict_of_costs:
                if param.units == "eq":
                    reagent_cost = (
                        dict_of_costs[param.name]
                        * param.value
                        * limiting_reagent_concentration
                        * slug_volume_l
                    )
                elif param.units == "mM":
                    reagent_cost = (
                        dict_of_costs[param.name] * param.value * slug_volume_l
                    )
                else:
                    continue  # Skip if units are not recognized for cost calculation
                total_cost += reagent_cost

        return total_cost

    def _calculate_throughput(self, recipe, yield_value):
        """
        Calculate throughput based on yield and residence time (mmol/h).
        """
        limiting_reagents = self._get_limiting_reagents()
        slug_size, _ = self._get_recipe_value(recipe, "slug_size", 500.0)
        slug_volume_l = slug_size * 1e-6  # Convert microliters to liters
        limiting_reagent_concentration = next(
            (param.value for param in recipe if param.name in limiting_reagents), 0
        )
        residence_time, residence_units = self._get_recipe_value(
            recipe, "residence_time"
        )

        if not all([residence_time, limiting_reagent_concentration, yield_value]):
            return 0

        # Convert residence time to hours
        if residence_units == "S":
            residence_time /= 3600
        elif residence_units == "min":
            residence_time /= 60

        throughput = (
            yield_value
            * limiting_reagent_concentration
            * slug_volume_l
            / residence_time
        )
        return throughput

    def _calculate_selectivity(
        self, yield_value, yield_sideproduct_a, yield_sideproduct_b
    ):
        """
        The selectivity is technically (by chemical engineering standard) the ratio between conversion and yield of
        desired product.
        However Simone says that for a chemist the selectivity is more interesting as the ratio between the desired
        product and the side products.

        to make this bounded between 0 and 1 we will use the following formula:
        selectivity = yield_value / (yield_value + yield_sideproduct_a + yield_sideproduct_b) (if the denominator is 0,
        return 0)
        """

        side_prod_sum = yield_sideproduct_a + yield_sideproduct_b + yield_value
        if side_prod_sum == 0:
            return 0

        selectivity = yield_value / side_prod_sum
        return selectivity

    def _calculate_light_power_efficiency(self, recipe, yield_value):
        """
        Calculate photon efficiency (mmol product per % of light power).
        """
        limiting_reagents = self._get_limiting_reagents()
        limiting_reagent_concentration = next(
            (param.value for param in recipe if param.name in limiting_reagents), 0
        )
        slug_size, _ = self._get_recipe_value(recipe, "slug_size", 500.0)
        slug_volume_l = slug_size * 1e-6  # Convert microliters to liters
        light_intensity, _ = self._get_recipe_value(recipe, "light_intensity")

        if not all([light_intensity, limiting_reagent_concentration, yield_value]):
            return 0

        photon_efficiency = (
            yield_value
            * limiting_reagent_concentration
            * slug_volume_l
            / light_intensity
        )
        return photon_efficiency

    def _calculate_cost_per_unit_product(self, recipe, yield_value):
        """
        Calculate the cost per unit product (Euro/mmol).
        """
        cost = self._calculate_cost(recipe)
        if yield_value == 0:
            return 0

        limiting_reagents = self._get_limiting_reagents()
        limiting_reagent_concentration = next(
            (param.value for param in recipe if param.name in limiting_reagents), 0
        )
        slug_size, _ = self._get_recipe_value(recipe, "slug_size", 500.0)
        slug_volume_l = slug_size * 1e-6  # Convert microliters to liters

        cpup = cost / (yield_value * limiting_reagent_concentration * slug_volume_l)
        return cpup

    def _calculate_mass_balance(self, recipe: list = None):
        """
        Calculates the mass balance as the sum of all the mmol of reagents used in the reaction.

        :param recipe: List of parameter objects containing chemical information, each with attributes
                       name, value, and units.
        :return: Total mass balance in mmol.
        """
        if recipe is None:
            return 0

        limiting_reagents = self._get_limiting_reagents()
        slug_size, _ = self._get_recipe_value(recipe, "slug_size", 500.0)
        slug_volume_l = slug_size * 1e-6  # Convert microliters to liters

        # Get limiting reagent concentration
        limiting_reagent_concentration = next(
            (param.value for param in recipe if param.name in limiting_reagents), 0
        )

        # Initialize mass balance with limiting reagent contribution
        mass_balance = slug_volume_l * limiting_reagent_concentration

        # Calculate mass balance for other reagents
        for param in recipe:
            if param.name not in limiting_reagents:
                if not hasattr(param, "units"):
                    continue
                if param.units == "eq":
                    mass_balance += (
                        param.value * limiting_reagent_concentration * slug_volume_l
                    )
                elif param.units == "mM":
                    mass_balance += param.value * slug_volume_l

        return mass_balance

    def _calculate_Elia_metric(self, recipe: list = None):
        """
        At this point it's a friday afternoon, i wanna go for beers and i have already written the code for the other metrics.
        I don't fkn know what the Elia metric is, so we're going to invent it on the spot.

        The Elia metric: take the values T for the residence time, M for the mass balance, C for the cost and L for the light power.

        EM = (ln(L+1)*(C+1)**(-0.5)*M/(T+1))^0.5      why?
            ln(L+1) introduces a diminishing return for the light power, as the light power increases the metric increases less and less.
            (C+1)**(-0.5) penalises high costs. The higher the cost the lower the metric.
            M/(T+1) is the mass balance per time, the higher the mass balance the better the metric, but we want it faster so we divide by the time.
            the square root is just because why not?

        :param recipe: List of parameter objects containing chemical information, each with attributes
                       name, value, and units.

        :return: Elia metric.
        """
        if recipe is None:
            return 0

        light_power, _ = self._get_recipe_value(recipe, "light_intensity")
        light_power = light_power / 100.0
        cost = self._calculate_cost(recipe)
        mass_balance = self._calculate_mass_balance(recipe)
        residence_time, _ = self._get_recipe_value(recipe, "residence_time")

        if not all([light_power, cost, mass_balance, residence_time]):
            return 0

        elia_metric = (
            np.log(light_power + 1)
            * (cost + 1) ** -0.5
            * mass_balance
            / (residence_time + 1)
        ) ** 0.5
        return elia_metric


class ML_Platform_omni(ToandFromMachine, ML_Platform):
    pass


class ML_Platform_HITL_omni(ToandFromMachine, ML_Platform_HITL):
    pass


class ML_Platform_HITL_Development_omni(ToandFromMachine, ML_Platform_HITL_Development):
    pass


class SingleBayesianOpti(ML_Platform_omni, SingleBayesianOptiBackend):
    pass


class SingleBayesianOptiHITL(ML_Platform_HITL_omni, SingleBayesianOptiBackend):
    """Single Bayesian Optimisation class, this class"""

    def __init__(self):
        super().__init__()


class EfficientBatchedBO_HITL(ML_Platform_HITL_omni, EfficientBatchedBOBackend):
    """Single Bayesian Optimisation class, this class"""

    def __init__(self):
        super().__init__()


class EfficientBatchedBO(ML_Platform_omni, EfficientBatchedBOBackend):
    """Single Bayesian Optimisation class, this class"""

    def __init__(self):
        super().__init__()


class MultiTaskScope_HITL(ML_Platform_HITL_omni, AllScopeTaskBackend):
    """
    this task is here to perform the mutli task optimization of a full scope at once
    """

    def __init__(self):
        super().__init__()


class ScopeAcceleratorTask(ML_Platform_omni, ScopeAcceleratorTaskBackend):
    """
    This is to perform a atransfer learning method between only 2 tasks. Gets data from task 1 and reuses it for task 2.
    """

    def __init__(self):
        super().__init__()


class EnantioExtravaganza(ML_Platform_HITL_omni, EnantioExtravaganzaBackend):
    """Single Bayesian Optimisation class, this class does a bunch of HITL points"""

    def __init__(self):
        super().__init__()


class MultiTaskScope(ML_Platform_omni, AllScopeTaskBackend):
    """
    this task is here to perform the mutli task optimization of a full scope at once
    """

    def __init__(self):
        super().__init__()


class DevHITL(ML_Platform_HITL_Development_omni, DevelopmentHITL):
    """Single Bayesian Optimisation class, this class"""

    def __init__(self):
        super().__init__()


class MyCustomML(ML_Platform_omni, MyCustomBackend):
    """Custom ML algorithm combining platform communication with custom backend logic."""

    def __init__(self):
        super().__init__()


class DragonflyML(ML_Platform_omni, DragonflyBackend):
    """Dragonfly GP Bandit ML algorithm combining platform communication with dragonfly backend logic."""

    def __init__(self):
        super().__init__()


