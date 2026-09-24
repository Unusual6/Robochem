"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr:

"""

from typing import Any

from robrains.base_classes import BaseParamClass


class AnalyParameter(BaseParamClass):
    """This is a class to represent an analytical parameter,
    it mostly acts like a dictionary with some added functionalities,
    such as storing the parameter name, the min and max values and the unit.
    it also stores the tag: "analytical_parameter"

    Members:
        -tag:
        -name:
        -min_value:


    """

    tag = "analytical_parameter"

    def __init__(
        self,
        name: str,
        unit: str,
        min_value: float = None,
        max_value: float = None,
        omni_tag: str = None,
        value: Any = None,
        allowed_values: list | None = None,
    ):
        """Initialises the analytical parameter object
        :param name: str: the name of the parameter
        :param min_value: float: the minimum value of the parameter
        :param max_value: float: the maximum value of the parameter
        :param unit: str: the unit of the parameter
        """

        self.name = name
        self.min_value = min_value
        self.max_value = max_value
        self.unit = unit
        self.style = "constant"
        self.omni_tag = omni_tag
        self.value = value
        self.low_bound = None
        self.high_bound = None
        self.allowed_values = allowed_values

    @classmethod
    def from_json(cls, json_data: dict):
        """initialises the class from a json dictionary"""
        try:
            instance = cls(
                name=json_data["name"],
                min_value=json_data["min_value"],
                max_value=json_data["max_value"],
                unit=json_data["unit"],
                omni_tag=json_data.get("omni_tag", None),
            )
            instance.value = json_data.get("value", None)
            instance.low_bound = json_data.get("low_bound", None)
            instance.high_bound = json_data.get("high_bound", None)
            instance.allowed_values = json_data.get("allowed_values", None)
            return instance
        except Exception as e:
            cls.log_mssg(
                f"Error initialising Analytical parameter from json: {e}", level="error"
            )
