"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr: Functions to save and load the session data.

"""

import json
import os
from typing import Any, Tuple, Dict, Literal, get_origin, get_args, Optional

import streamlit as st
from streamlit.runtime.state import SessionStateProxy

from robrains.base_classes import BaseLoggedClass, BaseParamClass
from robrains.parameter_backends import *

try:
    from backend.ml_backends import *
    from lamas.utils import LamaMethod, LamaParameter
except ImportError:
    pass

try:
    from ML.ml_modules import *
except ImportError:
    pass


class SessionContainer(BaseLoggedClass):
    """Since I absolutely Hate the session state of streamlit, we are gonna make our own session container:
    You may say, why do you do this, well streamlit overwrites the session state if you return to a page, which
    makes me absolutely furious. So we are gonna make one that we can update in a more deliberate way
    usage: use as you would a dictionary, with the added caveat that you can use the
    update_session(key, value, overwrite = True) method to update the session with the key value pair with or without overrwiting
    further on, it will NEVER overwrite a key:value pair if the  new value is None, "" or empty.

    finally we can use this to save and load previous sessions.

    Members:
        - _session: dict: the session container
        - _instance_cache: dict: cache for class instances to avoid duplicate initialisation
        -


    Methods:


    """

    _hide = True

    def __init__(self, session_init: SessionStateProxy = None):
        """initialise the session, this is done once as the backend is started"""
        self._session = {}
        self.do_not_save = []
        self.assertion_method(
            session_init,
            lambda x: isinstance(x, SessionStateProxy) or x is None,
            "session_init is not a streamlit session",
        )

        if session_init is not None:
            for key in session_init:
                self["key"] = session_init[key]

        self.log_mssg("Session container initialised", level="ok")

    def update_session(
        self, key: str, value: Any, overwrite: bool = True, force: bool = False
    ):
        """update the session with the key value pair:
        usage: update_session(key, value, overwrite = True, force = False)
        key: str: the key to update
        value: Any: the value to update
        overwrite: bool: whether to overwrite the key if it already exists
        force: bool: whether to force the update even if the value is None, "" or empty


        """

        if key is None or key == "":
            self.log_mssg("Key is None or empty, not updating", level="warning")
            return

        if key in self._session and not overwrite:
            self.log_mssg(
                f"Key {key} already in session, not overwriting", level="warning"
            )
            return

        # if the value is one of the parameters just need to check the bool statement:
        if isinstance(value, BaseParamClass) and not value:
            self.log_mssg(f"Value for key {key} is None, not updating", level="warning")
            return
        elif not isinstance(value, BaseParamClass) and (
            value is None or value == "" or value == [] or not value and not force
        ):
            self.log_mssg(
                f"Value for key {key} is None, empty or empty list, not updating",
                level="warning",
            )
            return
        if key == "experiment_path":
            self.log_mssg("Moving the logging directory to the new path", indent=1)
            self.log_mssg(
                "Old path: " + str(self._LOGGER._log_directory["log_directory"]),
                level="none",
                indent=2,
            )
            self.log_mssg("New path: " + str(value), level="none", indent=2)
            self.log_setter(os.path.join(value, "ML_logs"))

        self._session[key] = value
        self.log_mssg(f"Updated session with key {key}, value {value}", level="ok")

    def __getitem__(self, key: str):
        """method to access an item in the session_container.
        key: str, key to access
        """
        return self._session[key]

    def __setitem__(self, key: str, value: Any):
        """method to set an item in the session,
        key: str, key to access
        value: Any, value to set"""
        self._session[key] = value

    def __delitem__(self, key):
        """removes an item from the session"""
        del self._session[key]

    def __contains__(self, key):
        """returns if an item is present in the session"""
        return key in self._session

    def __iter__(self):
        """returns an iterable of the session"""
        return iter(self._session)

    def __len__(self):
        """returns the lenght of items in the session"""
        return len(self._session)

    def keys(self):
        """returns the keys available in the session"""
        return self._session.keys()

    def values(self):
        """returns the values in the session"""
        return self._session.values()

    def items(self):
        """returns the key:value pairs of the session"""
        return self._session.items()

    def get(self, key, default=None):
        """returns the value correspornign to the key, returns default if not availeble, instead of raising"""
        return self._session.get(key, default)

    def pop(self, key):
        """removes an item from the session"""
        self.log_mssg(f"Removing key {key} from session")
        return self._session.pop(key)

    @staticmethod
    def _has_tag_like_behavior(item):
        """Check if the item behaves like a dictionary regarding accessing a 'tag'."""
        return hasattr(item, "get")

    @staticmethod
    def _contains_tag(item, tag):
        """Check if the 'tag' is present in the item's 'tag' value, assuming the item behaves like a dictionary."""
        try:
            # Attempt to access 'tag' in a dictionary-like manner, defaulting to None if not present
            item_tags = item.get("tag", None)
            return tag in item_tags if item_tags is not None else False
        except Exception:
            # In case of any error (which shouldn't happen as we check has_tag_like_behavior first), treat as not containing the tag
            return False

    def search_by_tag(self, tag):
        """Search amongst the data for values that contain the keyword tag and return all the values
        that have the tag matching.
        param: tag: str: the tag to search for

        returns: list of keys that have the tag in the value
        """
        try:
            keys = [
                key
                for key in self._session
                if self._has_tag_like_behavior(self._session[key])
                and self._contains_tag(self._session[key], tag)
            ]

            if len(keys) == 0:
                self.log_mssg(f"No values found with tag {tag}", level="warning")

            return keys
        except Exception as e:
            self.log_mssg(f"Error searching by tag: {e}", level="error")
            return []

    @staticmethod
    def log_serialize(method):
        """Serialize is an annoying bit, so i want my thing to yell at me when it goes wrong"""

        def wrapper(self, *args, **kwargs):
            obj = args[0] if args else None
            self.log_mssg(f"Running {method.__name__} for {obj}")
            try:
                result = method(self, *args, **kwargs)
                self.log_mssg(
                    f"Successfully ran {method.__name__} for {obj}", level="ok"
                )
                return result
            except RecursionError as r:
                raise
            except Exception as e:
                self.log_mssg(
                    f"Error running {method.__name__} for {obj}: {e}", level="error"
                )
                raise

        return wrapper

    @staticmethod
    def serialise_type(type_obj: Any):
        """addon- serialises actual types to strings and returns them as dict

        :param type_obj: Any: the type object to serialise e.g. Literal("a", "b", "c")
        """

        origin = get_origin(type_obj)
        args = get_args(type_obj)

        if origin is Literal:
            return {"type": "Literal", "args": args}
        elif origin is Union:
            return {
                "type": "Union",
                "args": [SessionContainer.serialise_type(arg) for arg in args],
            }
        elif origin is List:
            return {
                "type": "List",
                "args": [SessionContainer.serialise_type(arg) for arg in args],
            }
        elif origin is Tuple:
            return {
                "type": "Tuple",
                "args": [SessionContainer.serialise_type(arg) for arg in args],
            }
        elif origin is Dict:
            return {
                "type": "Dict",
                "args": [SessionContainer.serialise_type(arg) for arg in args],
            }
        else:
            return {"type": str(type_obj)}

    @log_serialize
    def serialize_obj(self, obj: Any, parent: Optional[Any] = None) -> Any:
        """
        Recursively serialize nested objects into JSON‑safe primitives or markers.

        - Primitives (str, int, float, bool) and None pass through.
        - list/tuple/dict are recursed element‑wise.
        - User‑defined objects (having __dict__) become dicts with a "class" key
          plus their serialized attributes.
        - pandas.DataFrame objects are written out as CSV files in the session’s
          experiment_path and replaced by a marker string.

        For DataFrames, filenames are generated by:
          1) Inspecting `parent` to find an attribute whose value *is* this DataFrame.
          2) Naming the file `ParentClass_attrName.csv`.
          3) If no attribute matches, falling back to `ParentClass.csv`.

        Args:
            obj: Any Python object to serialize.
            parent: The parent instance under which `obj` lives, used to derive
                    the CSV filename.

        Returns:
            A JSON‑compatible primitive (None, bool, int, float, str, list, tuple, dict),
            or a special marker string for DataFrames, e.g. "@DataFrame]MyClass_df1.csv".
        """
        # 1. Base cases
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj

        # 2. DataFrame → write CSV + return marker
        if isinstance(obj, pd.DataFrame):
            # Must have a parent object to name the file
            if parent is None:
                return None

            # Derive class name
            class_name = parent.__class__.__name__

            # Try to find the attribute name on the parent that points to this DF
            attr_name = None
            for name, val in vars(parent).items():
                if val is obj and not name.startswith("_"):
                    attr_name = name
                    break

            # Build filename
            if attr_name:
                filename = f"{class_name}_{attr_name}.csv"
            else:
                filename = f"{class_name}.csv"

            filename = filename.replace("_df", "")

            # Save it
            csv_path = os.path.join(self._session["experiment_path"], filename)
            obj.to_csv(csv_path, index=False)

            # Return marker for JSON
            return f"@DataFrame]{filename}"

        # 3. Collections
        if isinstance(obj, list):
            return [self.serialize_obj(item, parent=parent) for item in obj]
        if isinstance(obj, tuple):
            return tuple(self.serialize_obj(item, parent=parent) for item in obj)
        if isinstance(obj, dict):
            return {
                key: self.serialize_obj(val, parent=parent) for key, val in obj.items()
            }

        # 4. User-defined objects
        if hasattr(obj, "__dict__"):
            # Special ML‑tagged objects
            if getattr(obj, "tags", None) and "ML" in getattr(obj, "tags", []):
                attrs = obj.get_data_to_save()
            else:
                attrs = obj.__dict__

            result: Dict[str, Any] = {"class": obj.__class__.__name__}
            for key, val in attrs.items():
                if key == "type":
                    result[key] = self.serialise_type(val)
                else:
                    # Pass the current object as the parent
                    result[key] = self.serialize_obj(val, parent=obj)
            return result

        # 5. Fallback for unknown types
        self.log_mssg(
            f"Cannot serialize object of type {type(obj)}: {obj}", level="warning"
        )
        return None

    def save_session(self, path: str = None):
        """save the session in a json by recursively iterating through each object and saving the members.
        param: path: str, path to save the json file, if none the json file is saved in the experiment path
        with name session.json"""
        try:
            # Write the session data as a JSON file
            if path is None or path == "":
                json_path = os.path.join(
                    self._session["experiment_path"], "session.json"
                )

            else:
                json_path = path

            # write the json path parent as the firstest thing:

            session_data = {}
            session_data["experiment_path"] = self.serialize_obj(
                self._session["experiment_path"]
            )

            skip = self.do_not_save + ["experiment_path"]
            for key, obj in self._session.items():
                if key in skip:
                    continue
                value = self.serialize_obj(obj)
                if value is not None:
                    session_data[key] = value

            with open(json_path, "w") as f:
                json.dump(session_data, f, indent=4)

            return "Success"
        except Exception as e:
            self.log_mssg(f"Error in saving the session: {e}", level="warning")
            raise e
            return "Error"

    def make_hashable(self, item):
        """Converts any data type into a hasahble, just to make sure we don't run into problems.."""
        if isinstance(item, (tuple, list)):
            return tuple(self.make_hashable(e) for e in item)
        elif isinstance(item, dict):
            return tuple((k, self.make_hashable(v)) for k, v in sorted(item.items()))
        else:
            return item

    def deserialize_obj(self, data, parent_class=None):
        """Deserialise the data form the json file, this also goes and loads csv where necessary. also initialises
        classes with relevant data when necessary.
        :param data: the data that we want to deserialise
        :param parent_class: the name of the class that holds the data."""
        if isinstance(data, dict):
            # If the data is a dictionary, there's a good chance it's part of a class that we should initialise
            if "class" in data:
                class_name = data.pop("class")
                cls = globals()[
                    class_name
                ]  # Get class type from globals based on class name
                hash_key = (cls, self.make_hashable(data))
                if hasattr(cls, "tags") and "ML" in cls.tags:
                    self.param_to_load.append((cls, data))
                    return None
                # Iterate through data items to handle possible DataFrames
                for key, value in list(data.items()):
                    if isinstance(value, str) and value.startswith("@DataFrame]"):
                        df_path = value.split("]", 1)[1]
                        df_path = os.path.join(
                            self._session["experiment_path"], df_path
                        )
                        data[key] = pd.read_csv(df_path)

                # Serialize data into a tuple for hashing in instance cache

                if hash_key in self._instance_cache:
                    return self._instance_cache[
                        hash_key
                    ]  # Return existing instance if available

                instance = cls.from_json(data)  # Create new instance from data
                self._instance_cache[hash_key] = instance  # Store new instance in cache
                return instance
            else:
                # Recursively handle dictionaries that don't represent a class instance
                return {
                    key: self.deserialize_obj(val, parent_class=parent_class)
                    for key, val in data.items()
                }
        elif isinstance(data, list):
            # Recursively handle lists
            return [
                self.deserialize_obj(item, parent_class=parent_class) for item in data
            ]
        else:
            return data

    def load_session(self, file: None = None, path: str = None):
        """Load the session from a JSON file and reconstruct the session objects.
        :param file: this is a file like object that we can read directly, if this is none we go for the path.
        :param path: reloads the data from the path, if path is none reloads from the experiment path:

        """
        try:
            if file is None:
                with open(path, "r") as f:
                    session_data = json.load(f)
            else:
                session_data = json.load(file)

            self._session = {}
            self._instance_cache = {}
            self.param_to_load = (
                []
            )  # Cache for class instances to avoid duplicate initialisation
            # first thing we need to serialise is the json path parent, so we can load the csvs
            exp_path = self.deserialize_obj(
                session_data.pop("experiment_path")
            )
            if exp_path == "":
                user = session_data["user_name"]
                experiment = session_data["experiment_name"]
                exp_path = os.path.join(os.path.expanduser("~"), "Robochem", user, experiment)
                if not os.path.exists(exp_path):
                    os.makedirs(exp_path)
            self._session["experiment_path"] = exp_path

            for key, data in session_data.items():
                value = self.deserialize_obj(data)
                if value is not None:
                    self._session[key] = value

            if hasattr(self, "param_to_load"):
                for cls, data in self.param_to_load:
                    data["exp_path"] = self._session["experiment_path"]
                    if "ML_parameters" in data.keys():
                        ml_param = [
                            self._session[name] for name in data["ML_parameters"]
                        ]
                        instance = cls.from_json(json_data=data, ml_parameters=ml_param)
                        self._session["experiment_class"] = instance
                    else:
                        # the ML class was not primed when saving, so we just make an instance and update the parameters
                        instance = cls.from_json(json_data=data)
                        self._session["experiment_class"] = instance
                del self.param_to_load

            vials_df = self._session.get("VialDF", None)
            if vials_df is not None:
                self._session["number_of_vials"] = vials_df.number_vials

            return "Success", ""
        except Exception as e:
            error_msg = str(e)
            self.log_mssg(f"Error in loading the session: {error_msg}", level="warning")
            # raise e
            return "Error", error_msg
