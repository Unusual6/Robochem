"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr: In the spirit of not repeating code here's a set of cosmetic functions for streamlit i can just call from the
streamlit pages. This allows for less repetition of code and better readability of the streamlit pages.

"""

import copy
from typing import Any, get_origin, get_args, Literal, Tuple, List, Dict

import streamlit as st
import pandas as pd
from PIL import Image
from robrains.parameter_backends import (
    Chemical,
    ML_parameter,
    PhysicalParameter,
    AnalyParameter,
    ExpParameter,
    StockSolutionDF,
    VialDF,
)

from omniplatypus.procedures.unit_tasks.sampling.liquid_handler_sampling import (
    GenerateSampleDataframe,
)

from lamas.utils import LamaMethod, LamaParameter


def ensure_backend():
    """
    Lazy-initialize PlatformBackend in st.session_state.
    Streamlit MPA v1 pre-loads pages before the main script runs, so the guard
    in robochem_flex.py may not have executed yet when a page first imports.
    Call this at the top of every page module to guarantee 'platform_backend'
    exists in session_state before any subsequent access.
    """
    if "platform_backend" not in st.session_state:
        try:
            from backend.platform_backend import PlatformBackend
            st.session_state["platform_backend"] = PlatformBackend(st.session_state)
        except Exception as exc:
            st.error(f"后端初始化失败: {exc}")
            st.info("请确认所有必需目录可写，并通过首页重新启动应用。")
            raise
    return st.session_state["platform_backend"]


def page_header():
    """
    page header setup:
    sets up the header page with the name of the platform and the logos, in this case the nrg and the omniplatypus logo
    """
    st.set_page_config(
        page_title="Robochem-Flex",
        page_icon="utils/NRG_icon.png",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": "### Robochem-Flex\n自动化化学实验平台，集成 OmniPlatypus 硬件与机器学习优化引擎。",
            "Get help": None,
            "Report a bug": None,
        },
    )

    # Title of the main page
    logo = Image.open("utils/NRG_logo.png")
    omni_logo = Image.open("utils/Omniplatypus.jpg")
    brains_logo = Image.open("backend/Robochem_ML/robrains/static/robrains.jpg")
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1], vertical_alignment="bottom")
    col1.title("Robochem-Flex")
    col2.image(
        logo,
        width=200,
    )
    col3.image(omni_logo, width=100)
    col4.image(brains_logo, width=100)

    st.markdown("_____")


def prettify_parameter_name(parameter_name: str):
    """Prettifies the parameter name by removing underscores and capitalising the first letter of each word
    :param parameter_name: the name of the parameter
    :returns: the prettified parameter name
    """

    return " ".join([word.capitalize() for word in parameter_name.split("_")])


def render_parameter_row(
    parameter_key: str,
    parameter_value: dict,
    parameter_data: PhysicalParameter,
    optional=False,
):
    """renders the checkbox for physical parameters, i want it to make also an input for the value if the parameter
    is to be set constant.
    :param parameter_key: the key of the parameter
    :param parameter_value: the value of the parameter as a dict in the form: {"min_value": float, "max_value": float, "unit": str}
    :param parameter_data: The data saved in the parameter in the SessionContainer, This is an instance of
    PhysicalParameter. Which stores the parameter data and the style of the parameter (constant or variable)
    usage: for parameter_key, parameter_value in st.session_state['physical_params'].items():
                parameter = render_parameter_row(parameter_key, parameter_value)


    """

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    # name of parameter:
    col1.write(prettify_parameter_name(parameter_key))
    choosable = ["variable", "constant"]
    # 单选按钮：设置参数为可变或恒定
    choiche = col2.radio(
        "设为恒定",
        ["variable", "constant"],
        format_func=lambda x: "可变" if x == "variable" else "恒定",
        index=choosable.index(
            parameter_data.get("style", "variable" if not optional else "constant")
        ),
        key=f"{parameter_key}_constant_status",
    )
    parameter_data["style"] = choiche
    # if the parameter is set to constant then let the user set the constant value:
    if choiche == "constant":
        value = col3.number_input(
            f"设置值 [{parameter_value['unit']}]",
            min_value=parameter_value["min_value"],
            max_value=parameter_value["max_value"],
            value=(
                parameter_data.get("value", parameter_value["min_value"])
                if parameter_data.get("value", parameter_value["min_value"]) is not None
                else parameter_value["min_value"]
            ),
            key=f"{parameter_key}_constant_value",
        )

        parameter_data["value"] = value

    # return parameter_data


def render_exp_parameter_row(
    parameter_key: str,
    parameter_value: dict,
    parameter_data: ExpParameter,
    optional=False,
):
    """
    renders a row for the experimental parameter, asks the user if they want to
    modify the default value by clicking a checkbox and then lets the user modify the value
    depending on the type of value of the parameter it decides wheter it needs to be a
    number input, a text input, a check box or a select box

    returns either save or don't save is the user decides to modify the parameter or not
    """
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    col1.write(prettify_parameter_name(parameter_key))
    if col2.checkbox("修改", value=False, key=f"{parameter_key}_modify"):
        # check the type of the parameter value:
        if parameter_value["value"] == True or parameter_value["value"] == False:
            new_value = col3.checkbox(
                f"是",
                value=parameter_data.value,
                key=f"{parameter_key}_constant_value",
            )
            parameter_data.value = new_value
            return "save"

        match parameter_value["value"]:
            case int() | float():
                unit = parameter_value.get("unit", None)
                new_value = col3.number_input(
                    f"设置值 [{unit if unit is not None else '-'}]",
                    value=parameter_data.value,
                    key=f"{parameter_key}_constant_value",
                )

            case str():
                if parameter_value.get("allowed_values", None) is not None:
                    new_value = col3.selectbox(
                        f"设置值",
                        options=parameter_value["allowed_values"],
                        key=f"{parameter_key}_constant_value",
                    )
                else:
                    new_value = col3.text_input(
                        f"设置值",
                        value=parameter_data.value,
                        key=f"{parameter_key}_constant_value",
                    )
            case _:
                st.warning("不支持的参数类型")
                return "don't save"

        parameter_data.value = new_value
        return "save"
    else:
        return "don't save"


def render_analytical_parameter(parameter_key: str, parameter_data: AnalyParameter):
    """renders a number input for the analytical parameters, it gives the analytical parameter, and lets the user
    choose the value. For now all the analytical parameters are set to constants.
    :param parameter_key: the key of the parameter
    :param parameter_data: The data saved in the parameter in the SessionContainer, This is an instance of the AnalyticalParameter.
    """
    col1, col2, col3 = st.columns([1, 1, 1])
    col1.write(prettify_parameter_name(parameter_key))

    unit_string = (
        f"[{parameter_data.unit}]" if parameter_data.unit not in ["", None] else ""
    )
    # check which type the current parameter value is:
    if parameter_key == "yield_calculation_chemical":
        new_value = col2.selectbox(
            f"设置值 {unit_string}",
            options=Chemical.available_purposes,
            key=f"{parameter_key}_constant_value",
            index=(
                Chemical.available_purposes.index(parameter_data.value)
                if parameter_data.value in Chemical.available_purposes
                else 0
            ),
        )
    elif parameter_key == "target_peak":
        use_dataframe = col2.checkbox("添加多个？", key=f"{parameter_key}_multiple")

        if isinstance(parameter_data.value, pd.DataFrame):
            use_dataframe = True

        if use_dataframe:
            # Get available chemical names
            chemical_names = st.session_state[
                "platform_backend"
            ].session_container.search_by_tag("chemical")

            # Load existing value or create an empty DataFrame
            if not isinstance(parameter_data.value, pd.DataFrame):
                param_data_value = pd.DataFrame(
                    {"Chemical": ["A"], "peak_position(ppm)": [1.0]}
                )

            else:
                param_data_value = copy.deepcopy(parameter_data.value)

            # Ensure "Chemical" column defaults to empty string instead of NaN
            # Create Data Editor with constraints
            param_data = col2.data_editor(
                param_data_value,
                key=f"{parameter_key}_multiple_editor",
                num_rows="dynamic",
                column_config={
                    "Chemical": st.column_config.SelectboxColumn(
                        "Chemical",
                        options=chemical_names,
                        required=True,
                        default=chemical_names[0] if chemical_names else "",
                    ),
                    "peak_position(ppm)": st.column_config.NumberColumn(
                        "peak_position(ppm)", required=True
                    ),
                },
            )

            if col2.button("保存", key=f"{parameter_key}_save"):
                param_data = param_data.dropna(
                    subset=["Chemical"]
                )  # Remove rows where "Chemical" is NaN
                param_data = param_data[
                    param_data["Chemical"] != ""
                ]  # Remove empty string rows
                param_data.reset_index(
                    drop=True, inplace=True
                )  # Reset index to avoid gaps
                new_value = param_data.copy()
                st.write(new_value)  # Ensure we store a copy of the updated DataFrame
            else:
                new_value = (
                    parameter_data.value
                )  # Keep the original value if not saving

        else:
            # If not using a DataFrame, allow input of a single float
            new_value = col2.number_input(
                f"设置值 {unit_string}",
                min_value=parameter_data.min_value,
                max_value=parameter_data.max_value,
                value=(
                    parameter_data.value
                    if isinstance(parameter_data.value, (int, float))
                    else 0.0
                ),
                key=f"{parameter_key}_constant_value",
            )

    elif parameter_key == "retention_time":
        use_dataframe = col2.checkbox("添加多个？", key=f"{parameter_key}_multiple")

        if isinstance(parameter_data.value, pd.DataFrame):
            use_dataframe = True

        if use_dataframe:
            # Get available chemical names
            chemical_names = st.session_state[
                "platform_backend"
            ].session_container.search_by_tag("chemical")

            # Load existing value or create an empty DataFrame
            if not isinstance(parameter_data.value, pd.DataFrame):
                parameter_data.value = pd.DataFrame(
                    {"Chemical": [], "Retention time (min)": []}
                )

            param_data_value = copy.deepcopy(parameter_data.value)

            # Ensure "Chemical" column defaults to empty string instead of NaN

            # Create Data Editor with constraints
            param_data = col2.data_editor(
                param_data_value,
                key=f"{parameter_key}_multiple_editor",
                num_rows="dynamic",
                column_config={
                    "Chemical": st.column_config.SelectboxColumn(
                        "Chemical",
                        options=chemical_names,
                        required=True,
                        default=chemical_names[0] if chemical_names else "",
                    ),
                    "Retention time (min)": st.column_config.NumberColumn(
                        "Retention time (min)", required=True
                    ),
                },
            )

            if col2.button("保存", key=f"{parameter_key}_save"):
                # Remove any rows where "Chemical" is empty (to avoid storing invalid rows)
                new_value = param_data
            else:
                new_value = (
                    parameter_data.value
                )  # Update value with the edited DataFrame

        else:
            # If not using a DataFrame, allow input of a single float
            parameter_data.value = col2.number_input(
                f"设置值 {unit_string}",
                min_value=parameter_data.min_value,
                max_value=parameter_data.max_value,
                value=(
                    parameter_data.value
                    if isinstance(parameter_data.value, (int, float))
                    else 0.0
                ),
                key=f"{parameter_key}_constant_value",
            )

    elif parameter_data.allowed_values is not None:
        new_value = col2.selectbox(
            f"设置值 {unit_string}",
            options=parameter_data.allowed_values,
            key=f"{parameter_key}_constant_value",
            index=(
                parameter_data.allowed_values.index(parameter_data.value)
                if parameter_data.value is not None
                else 0
            ),
        )
    elif isinstance(parameter_data.value, int | float | None):
        new_value = col2.number_input(
            f"设置值 {unit_string}",
            min_value=parameter_data.min_value,
            max_value=parameter_data.max_value,
            value=parameter_data.value,
            key=f"{parameter_key}_constant_value",
        )
    else:
        new_value = col2.text_input(
            f"设置值 {unit_string}",
            value=parameter_data.value,
            key=f"{parameter_key}_constant_value",
        )

    # update the value in the parameter:
    parameter_data.value = new_value


def prettify_purpose_names(purpose: list):
    """Prettifies the purpose name by removing underscores and capitalising the first letter of each word
    :param purpose: list the name of the purpose
    :returns: the prettified purpose name
    """

    return [prettify_parameter_name(p) for p in purpose]


def display_chemical_inputs(chem_class: Chemical, i=0):
    """
    Displays a table of input fields for defining the chemical species.
    :chem_class: Chemical: class of parameter type for a chemical species
    :i: int: index of the chemical species

    returns: Chemical: instance of the chemical species (with filled data)
    """
    with st.container():
        cols = st.columns([3, 3, 3, 3, 3])
        name = cols[0].text_input(
            "名称",
            key=f"name-{i}",
            value=chem_class.name if chem_class.name is not None else "",
            help="试剂的可读名称",
        )
        identifier_type = cols[1].selectbox(
            "标识符类型",
            Chemical.available_IDs,
            key=f"id_type-{i}",
            index=(
                chem_class.available_IDs.index(chem_class.identifier_type)
                if chem_class.identifier_type is not None
                else 0
            ),
            help="选择用于记录的唯一标识符类型",
        )
        identifier = cols[2].text_input(
            "标识符",
            key=f"identifier-{i}",
            value=chem_class.identifier if chem_class.identifier is not None else "",
            help="输入唯一试剂标识符的值",
        )
        purpose = cols[3].selectbox(
            "用途",
            Chemical.available_purposes,
            key=f"purpose-{i}",
            index=(
                chem_class.available_purposes.index(chem_class.purpose)
                if chem_class.purpose is not None
                else 0
            ),
            help="选择该试剂在反应中的角色",
        )
        if purpose == "Constant":
            st.write("请为恒定化学物质提供数值")
            value = cols[4].number_input(
                "浓度 (mM)",
                key=f"value-{i}",
                min_value=0.0,
                value=chem_class.value if chem_class.value is not None else 0.0,
            )
        elif st.session_state["platform_backend"].session_container["price"] == "Yes":
            price = cols[4].number_input(
                "价格 (€/mmol)",
                key=f"price-{i}",
                min_value=0.0,
                value=chem_class.price if chem_class.price is not None else 0.0,
                help="输入化学物质价格，单位为 €/mmol",
            )
        # Assume here we want to create an instance of Chemical
        if all(
            [name, identifier_type, identifier, purpose]
        ):  # Check if all necessary fields are filled
            chem_class.update_values(
                name=name,
                identifier_type=identifier_type,
                identifier=identifier,
                purpose=purpose,
            )
            if purpose == "constant":
                chem_class["value"] = value
            elif (
                st.session_state["platform_backend"].session_container["price"] == "Yes"
            ):
                chem_class["price"] = price
            # st.write(chem_class)
        elif not name:
            chem_class.name = None


def initialize_or_update_StockDF():
    """Initializes or updates the 'StockDF' in the session container based on current state."""
    backend = st.session_state["platform_backend"].session_container
    list_of_chemicals = backend.search_by_tag("chemical")

    # Separate the list of chemicals into chemicals and solvents:
    chemicals = [
        key for key in list_of_chemicals if backend.get(key).purpose != "Solvent"
    ]
    solvents = [key for key in list_of_chemicals if key not in chemicals]

    if "StockDF" not in backend:
        backend["StockDF"] = StockSolutionDF(
            chemicals_list=chemicals, solvent_list=solvents
        )
    else:
        backend["StockDF"].update_df(
            new_chemicals_list=chemicals, new_solvent_list=solvents
        )


def configure_column_config(df, StockDF_object):
    """Generates the column configuration for the data editor and stores it in session state."""

    # Create a new configuration only if the columns have changed or if it's the first time
    if "column_config" not in st.session_state or set(
        st.session_state["column_config"].keys()
    ) != set(df.columns):
        column_config = {
            key: st.column_config.NumberColumn(
                f"{key} (mM)",
                help=f"添加化学物质 {key.split('_')[-1]} 在储备溶液中的浓度 (mM)",
                min_value=0.0,
                default=0.0,
            )
            for key in df.columns
            if key not in ["StockID", "Solvent"]
        }

        column_config["Solvent"] = st.column_config.SelectboxColumn(
            "溶剂",
            options=(
                StockDF_object.solvent_list
                if StockDF_object.solvent_list
                else ["溶剂？"]
            ),
            help="选择储备溶液的溶剂",
            default=(
                StockDF_object.solvent_list[0]
                if StockDF_object.solvent_list
                else "溶剂？"
            ),
        )

        # Add StockID with dynamic generation logic
        column_config["StockID"] = st.column_config.TextColumn(
            "储备溶液 ID",
            help="输入储备溶液的名称",
            disabled=False,
            default=StockDF_object.generate_name(),
        )

        # Store the column configuration in session state
        st.session_state["column_config"] = column_config
    else:
        column_config = st.session_state["column_config"]

    return column_config


def configure_data_editor(StockDF_object: StockSolutionDF, stock_column: st.columns):
    """Configures and displays the data editor for the StockDF."""

    # Get the DataFrame from StockDF
    df = StockDF_object.df.copy().reset_index(drop=True)

    # Use the column configuration from session state, or generate a new one if needed
    column_config = configure_column_config(df, StockDF_object)

    # Show the data editor with the cached or newly generated column configuration
    edited_df = stock_column.data_editor(
        df, column_config=column_config, num_rows="dynamic", key="stock_df_editor"
    )

    # Save the edited DataFrame back to the session state
    st.session_state["edited_df"] = edited_df

    return edited_df


def handle_stock_solutions(stock_column: st.columns):
    """Main function to manage stock solutions in the session state and UI."""
    initialize_or_update_StockDF()
    StockDF = st.session_state["platform_backend"].session_container["StockDF"]

    # Display the data editor and get the edited DataFrame
    edited_df = configure_data_editor(StockDF, stock_column)

    # Ensure columns match between edited_df and StockDF.df
    if set(edited_df.columns) != set(StockDF.df.columns):
        st.warning(
            "列已发生变化，正在重置为当前的 StockDF。"
        )
        edited_df = (
            StockDF.df.copy()
        )  # Reset the displayed DataFrame to the current StockDF if columns have changed

    # Reorder columns to match StockDF.df
    edited_df = edited_df[StockDF.df.columns]

    # Validation of the displayed DataFrame
    if edited_df.drop(columns="StockID").eq(0.0).all(axis=1).any():
        st.warning("所有储备溶液至少需要一种化合物！")
        submit_button_visible = False
    elif edited_df["StockID"].isnull().any():
        st.warning("请为每种储备溶液提供名称。")
        submit_button_visible = False
    elif edited_df["StockID"].duplicated().any():
        st.warning("储备溶液 ID 必须唯一，更改将不会保存。")
        submit_button_visible = False
    else:
        submit_button_visible = True

    # Only show the submit button if everything is valid
    if submit_button_visible:
        if st.button("提交储备溶液"):
            StockDF.update_from_df(edited_df)
            st.session_state["platform_backend"].session_container["StockDF"] = StockDF
            st.success("储备溶液更新成功！")

    # Optionally display the current StockDF in a collapsible section
    with st.expander("显示当前储备溶液详情"):
        st.write(StockDF.df)


def initialise_or_update_VialDF():
    """Initializes or updates the VialDF in the session container."""
    backend = st.session_state["platform_backend"].session_container
    number_of_vials = backend.get("number_of_vials", 1)
    stocks_df = backend.get("StockDF", None)
    handler_info = st.session_state["platform_backend"].get_handlers(
        st.session_state["platform_backend"].session_container["platform_name"]
    )
    if stocks_df is None:
        st.warning("请先配置储备溶液")
        return

    if "VialDF" not in backend:
        backend["VialDF"] = VialDF(
            number_vials=number_of_vials,
            stock_df=stocks_df,
            handler_info=handler_info,
        )
    else:
        backend["VialDF"].get_stock_info(stocks_df)
        backend["VialDF"].get_handler_info(handler_info)
        backend["VialDF"].update_df(new_number_of_samples=number_of_vials)


def configure_vial_column_config(VialDF_object):
    """Generates and saves column configuration for VialDF."""
    backend = st.session_state["platform_backend"].session_container
    number_of_vials = backend.get("number_of_vials", 1)
    current_columns = VialDF_object.df.columns

    # Recreate configuration only if columns have changed or if it hasn't been created before
    if (
        "vial_column_config" not in st.session_state
        or set(st.session_state["vial_column_config"].keys()) != set(current_columns)
        or "vial_number" not in st.session_state
        or st.session_state["vial_number"] != number_of_vials
    ):
        column_config = {
            "VialName": st.column_config.TextColumn(
                "样品瓶名称", help="输入样品瓶的名称"
            ),
            "StockID": st.column_config.SelectboxColumn(
                "储备溶液",
                options=VialDF_object.stock_list + VialDF_object.solvent_list,
                help="选择样品瓶对应的储备溶液",
                default="Not a Stock",
            ),
            "Volume": st.column_config.NumberColumn(
                "体积 (uL)",
                min_value=0.0,
                help="输入样品瓶中储备溶液的体积，单位为 uL",
            ),
            "Type": st.column_config.SelectboxColumn(
                "类型",
                options=VialDF_object.sample_type,
                help="选择样品瓶的类型",
                default="Solvent",
            ),
            "Sampler": st.column_config.SelectboxColumn(
                "液体处理器",
                options=VialDF_object.available_handlers,
                help="选择样品瓶对应的液体处理器",
                default=VialDF_object.available_handlers[-1],
            ),
            "Holder": st.column_config.SelectboxColumn(
                "样品架",
                options=VialDF_object.available_holders,
                help="选择样品瓶对应的样品架",
                default=VialDF_object.available_holders[0],
            ),
            "Position": st.column_config.SelectboxColumn(
                "位置",
                options=VialDF_object.available_positions,
                help="输入样品瓶在样品架中的位置",
                default="A1",
            ),
            "Counter": st.column_config.NumberColumn(
                "穿刺计数",
                help="隔垫穿刺计数器",
                default=0,
            ),
            "Viable": st.column_config.CheckboxColumn(
                "可用",
                help="切换以设置样品瓶是否可供机器使用",
                default=True,
            ),
        }

        # Save the column config and number of vials in session state
        st.session_state["vial_column_config"] = column_config
        st.session_state["vial_number"] = number_of_vials

    return st.session_state["vial_column_config"]


def handle_vials():
    """
    Main function to handle the vial configuration data editor.
    Updates VialDF only after a button is pressed.
    """

    # First, initialize the Vial DataFrame
    initialise_or_update_VialDF()

    VialDF_object = st.session_state["platform_backend"].session_container["VialDF"]

    # Generate or retrieve the column configuration for the vial data editor
    column_config = configure_vial_column_config(VialDF_object)

    # Display the vial editor with the column config
    edited_vial_df = st.data_editor(
        VialDF_object.df,
        column_config=column_config,
        hide_index=True,
        disabled=["VialID"],
        num_rows="dynamic",
        key="vial_df_editor",
        width="stretch",
    )

    # Button to trigger updating the VialDF
    if st.button("提交样品瓶配置"):
        ret = VialDF_object.update_from_df(edited_vial_df)
        if ret is not None and ret["level"] == "warning":
            st.warning(f"当前样品瓶配置存在问题：{ret['message']}")
        else:
            st.session_state["platform_backend"].session_container[
                "VialDF"
            ] = VialDF_object
            st.success("样品瓶配置更新成功！")

    # Optionally show the current state of the VialDF
    with st.expander("显示当前样品瓶详情"):
        st.write(VialDF_object.df)


def initialise_ml_parameters():
    """initialises the ml parameters so we have a set of parameters in the session state:
    all the parameters are instances of the ml_parameter class and for the chemical they store
    all the available chemicals for each type. The ml_parameter also stores if the parameter is
    discrete, continuous or both (i.e. Chemical and chemical conc), it's units and
    if it's a physical param or a chemical"""
    try:
        backend = st.session_state["platform_backend"]
    except KeyError:
        st.warning(
            "未检测到已启动的后端，请重启平台后再试。"
        )

    chemicals = backend.session_container.search_by_tag("chemical")
    physical_params = backend.session_container.search_by_tag("physical")
    # Initialize dictionaries for quick lookup and storage
    chemicals_by_type = {}
    existing_parameters = set()  # Store existing parameters to avoid redundancy

    # Process each chemical only once
    for chem in chemicals:
        chem_data = backend.session_container[chem]
        if chem_data.purpose in ["Solvent", "Constant"]:
            continue  # Skip solvents and constants

        chem_type = chem_data.purpose
        if chem_type not in chemicals_by_type:
            chemicals_by_type[chem_type] = []

        chemicals_by_type[chem_type].append(chem)

    # Now, update the discrete values for each type in one go
    for chem_type, chems in chemicals_by_type.items():
        param_name = f"{chem_type}_ml"
        if param_name in backend.session_container:
            # Assuming update_values is a method to add discrete values to an existing parameter
            backend.session_container[param_name].update_values(discrete=chems)
        else:
            backend.session_container[param_name] = backend.ml_parameter(name=chem_type)
            backend.session_container[param_name].update_values(discrete=chems)
        if backend.session_container["price"] == "Yes":
            prices = {chem: backend.session_container[chem].price for chem in chems}
            backend.session_container[param_name].update_values(prices=prices)

    # Process physical parameters similarly, ensuring to avoid redundancy
    for phys in physical_params:
        phys_data = backend.session_container[phys]
        if phys_data.style == "constant":
            continue  # Skip constants

        param_name = f"{phys}_ml"
        if param_name not in backend.session_container:
            backend.session_container.update_session(
                param_name,
                backend.ml_parameter(
                    name=phys,
                    parent_parameter=phys_data,
                ),
            )
        if param_name not in existing_parameters:
            existing_parameters.add(param_name)

    # search all the ML parameters and remove the ones where the parent parameter is not in the session container (only for
    # physical parameters)
    for ml_param in backend.session_container.search_by_tag("ML_parameter"):
        ml_param_instance = backend.session_container[ml_param]
        if (
            ml_param_instance.phy_chem == "Physical"
            and ml_param_instance.name not in physical_params
        ):
            backend.session_container.pop(ml_param)


def display_ml_chem_param(ml_parameter: ML_parameter):
    """Display the ml_chemical parameter, it displays the name of the parameter and lets you set in
    the input box for the min and max value for the parameter"""

    current_const = ml_parameter.constant_valued
    if current_const == False:
        col_name, col_min, col_max, col_const = st.columns(
            [1, 1, 1, 1], vertical_alignment="bottom"
        )
        col_name.write(ml_parameter.name)

        min_value = col_min.number_input(
            f"最小值 [{ml_parameter.unit}]",
            min_value=0.0,
            value=ml_parameter.min_value if ml_parameter.min_value is not None else 0.0,
            step=0.000001,
            format="%0.6f",
            key=f"{ml_parameter.name}_min",
            help=f"{ml_parameter.name.lower()} 用量不低于此值",
        )
        max_value = col_max.number_input(
            f"最大值 [{ml_parameter.unit}]",
            min_value=0.0,
            value=ml_parameter.max_value if ml_parameter.max_value is not None else 0.0,
            step=0.000001,
            format="%0.6f",
            key=f"{ml_parameter.name}_max",
            help=f"{ml_parameter.name.lower()} 用量不高于此值",
        )

        const: bool = col_const.checkbox(
            f"设为恒定值",
            value=current_const,
            key=f"constant_valued{ml_parameter.name}",
        )
        ml_parameter.constant_valued = const
        ml_parameter.update_values(min_value=min_value, max_value=max_value)

    else:
        col_name, col_val, col_const = st.columns(
            [1, 1, 1], vertical_alignment="bottom"
        )
        col_name.write(ml_parameter.name)

        const_val = col_val.number_input(
            f"恒定值 [{ml_parameter.unit}]",
            step=0.00001,
            format="%0.6f",
            value=(
                ml_parameter.const_value
                if ml_parameter.const_value is not None
                else 0.0
            ),
        )

        const: bool = col_const.checkbox(
            f"设为恒定值",
            value=current_const,
            key=f"const_val_{ml_parameter.name}",
        )
        ml_parameter.constant_valued = const
        ml_parameter.update_values(const_value=const_val)


def display_physical_ml_parameters(ml_physical: ML_parameter):
    """Display the physical ml parameters, it displays the name of the parameter and lets you set in
    the input box for the min and max value for the parameter"""
    col_name, col_method, col_min, col_max = st.columns([1, 1, 1, 1])
    friendly_name = ml_physical.name.replace("_", " ").capitalize()
    col_name.write(friendly_name)
    method = col_method.radio(
        "连续或离散",
        ["Continuous", "Discrete"],
        index=(
            ["Continuous", "Discrete"].index(ml_physical.discrete_continuous)
            if hasattr(ml_physical, "discrete_continuous")
            else 0
        ),
        key=f"{ml_physical.name}_method",
        format_func=lambda x: "连续" if x == "Continuous" else "离散",
    )

    if method == "Continuous":
        ml_physical.discrete_continuous = "Continuous"
        min_value = col_min.number_input(
            f"最小值 [{ml_physical.unit}]",
            min_value=ml_physical.default_min,
            max_value=ml_physical.default_max,
            step=0.000001,
            format="%0.6f",
            value=(
                ml_physical.min_value
                if ml_physical.min_value is not None
                else ml_physical.default_min
            ),
            key=f"{ml_physical.name}_min",
            help=f"{friendly_name} 设置值不低于此",
        )
        max_value = col_max.number_input(
            f"最大值 [{ml_physical.unit}]",
            max_value=ml_physical.default_max,
            min_value=ml_physical.default_min,
            step=0.000001,
            format="%0.6f",
            value=(
                ml_physical.max_value
                if ml_physical.max_value is not None
                else ml_physical.default_max
            ),
            key=f"{ml_physical.name}_max",
            help=f"{friendly_name} 设置值不高于此",
        )
        ml_physical.update_values(min_value=min_value, max_value=max_value)
    elif method == "Discrete":
        ml_physical.discrete_continuous = "Discrete"
        discrete = col_min.text_input(
            f"离散值 [{ml_physical.unit}]",
            ml_physical.discrete_str if ml_physical.discrete_str is not None else "",
            key=f"{ml_physical.name}_discrete",
        )
        ml_physical.validate_and_update(discrete=discrete)


def display_ml_parameters():
    """
    Displays the input parameters for the machine learning model (adaptive, depends on the ml model chosen)
    """
    backend = st.session_state["platform_backend"]
    if backend.ml_experiment_class is None:
        st.warning("机器学习模型尚未初始化，请先在「运行平台」页面启动平台。")
        return
    ml_parameters = backend.ml_experiment_class.input_parameters

    # Define simple parameters
    simple_params = [
        "Number of initial points",
        "Number of total points",
        "Number of Experiments per batch",
    ]
    # 中文标签映射
    simple_param_labels = {
        "Number of initial points": "初始实验点数",
        "Number of total points": "总实验点数",
        "Number of Experiments per batch": "每批次实验数",
    }

    # Function to render parameter row
    def render_parameter_row(param_key, param_value, current_param):
        if param_value == "int":
            value = input_number(
                name=param_key,
                min_value=0,
                max_value=10000,
                value=current_param if current_param is not None else 0,
            )
        elif param_value == "float":
            value = input_number(
                name=param_key,
                min_value=0.0,
                max_value=100.0,
                value=current_param if current_param is not None else 0.0,
            )
        elif isinstance(param_value, list):
            value = input_selectbox(
                name=param_key,
                options=param_value,
                key=param_key,
                default=current_param if current_param is not None else None,
            )
            if len(backend.session_container["objectives"]) > 1 and value in [
                "UCB",
                "EI",
                "PI",
                "qMEV",
            ]:
                st.error(
                    f"{value} 仅适用于单目标优化，请选择其他采集函数"
                )
            elif len(backend.session_container["objectives"]) == 1 and value in [
                "EHVI",
                "qEHVI",
            ]:
                st.error(
                    f"{value} 仅适用于多目标优化，请选择其他采集函数"
                )
        elif param_value == "bool":
            value = st.checkbox(
                param_key,
                current_param if current_param is not None else False,
                key=param_key,
            )
        elif param_value == "list":
            value = st.text_input(
                param_key,
                current_param if current_param is not None else "",
                key=param_key,
            )
        if param_value in ["json", "csv", "txt", "pickle"]:
            value = input_file(name=param_key, filetype=param_value, key=param_key)
            backend.ml_experiment_class.load_file_data(param_key, value)
        else:
            backend.ml_experiment_class.validate_and_update(param_key, value)

    # Display simple parameters first
    for simple_param in simple_params:
        if simple_param in ml_parameters:
            current_param = backend.ml_experiment_class.parameters.get(
                simple_param, None
            )
            render_parameter_row(
                simple_param_labels.get(simple_param, simple_param), ml_parameters[simple_param], current_param
            )

    # Use expander for other parameters
    with st.expander("显示高级参数"):
        for ml_param_key, ml_param_value in ml_parameters.items():
            if ml_param_key not in simple_params:
                current_param = backend.ml_experiment_class.parameters.get(
                    ml_param_key, None
                )
                render_parameter_row(ml_param_key, ml_param_value, current_param)


def display_platform_df(platform_df: pd.DataFrame):
    edited_df = st.data_editor(
        data=platform_df,
        column_config={col: None for col in GenerateSampleDataframe.overridden_columns},
        num_rows="dynamic",
        key="fixing_platform_df",
    )
    return edited_df


def input_number(
    name: str, min_value: float = 0, max_value: float = 100, value: float = None
):
    """
    input number function, this function is used to input a number in the streamlit page
    :param name: str: the name of the number
    :param min_value: float: the minimum value of the number
    :param max_value: float: the maximum value of the number
    :param key: str: the key of the number
    :returns: float: the value of the number
    """
    return st.number_input(
        name, min_value=min_value, max_value=max_value, key=name, value=value
    )


def input_selectbox(name: str, options: list, key: str, default: str = None):
    """
    input selectbox function, this function is used to input a selectbox in the streamlit page
    :param name: str: the name of the selectbox
    :param options: list: the options of the selectbox
    :param key: str: the key of the selectbox
    :returns: str: the value of the selectbox
    """
    return st.selectbox(
        name,
        options,
        key=key,
        index=options.index(default) if default is not None else 0,
    )


def input_file(name: str, filetype: str = "json", key: str = None):
    """
    input file function, this function is used to input a file in the streamlit page
    :param name: str: the name of the file
    :param filetype: str: the type of the file
    :param key: str: the key of the file
    :returns: file: the value of the file
    """
    st.write(f"请上传 {name} 的 {filetype} 文件")
    return st.file_uploader(name, type=[filetype], key=key)


def display_sample_and_stock_solution_ui(position: str = "reagents"):
    # Stock Solutions Section
    backend = st.session_state["platform_backend"]
    st.subheader("储备溶液")

    reagent_text1 = (
        "试剂从已知浓度的储备溶液中取样。\n"
        "请在下表中填写每种化学物质在各储备溶液中的浓度。\n"
        "可以在同一溶液中添加多种试剂，但这会限制反应混合物中的相对浓度比例，请注意这一点。"
    )
    reagent_text2 = (
        "如果修正当前平台错误需要重新配制一个或多个储备溶液，请在此处修改。\n"
    )
    st.markdown(reagent_text1 if position == "reagents" else reagent_text2)
    st.write("")

    # Display and load the stock solutions
    stock_col1 = st.columns([1])[0]
    handle_stock_solutions(stock_col1)

    # Sample Vials and Volumes Section
    st.subheader("样品瓶和体积")
    vial_text1 = (
        "此表格必须列出平台可用的所有样品瓶，包括其位置、体积和内容物。"
    )
    vial_text2 = (
        "如果修正当前平台错误需要重新装填或修改样品瓶，请在此处修改。\n"
    )
    st.write(vial_text1 if position == "reagents" else vial_text2)

    st.markdown(
        "### 详细说明 \n"
        "1. 选择您打算放入样品架中的样品瓶数量，包括：a. 溶剂、"
        "b. 废液、c. 试剂、d. 样品（用于接收处理器）、e. 清洗液。\n"
        "2. 每添加一个样品瓶会生成一行，带有一个哈希值（该值唯一，您无需关心）。\n"
        "3. 填写样品瓶的详细信息：\n"
        "    1. `样品瓶名称`（选择的内部跟踪名称，例如「起始物料瓶」）\n"
        "    2. `液体处理器`（样品瓶位于哪个液体处理器，例如 Handler_1）\n"
        "    3. `样品架`（样品瓶位于哪个样品架，例如 Holder_A）\n"
        "    4. `位置`（样品瓶在样品架中的位置，例如 A1）\n"
        "    5. `类型`（样品瓶的用途，例如 溶剂、储备液 或 样品）\n"
        "    6. `储备溶液`（如果样品瓶是试剂，它包含哪个储备溶液，例如 Stock_SM）\n"
        "    7. `体积`（样品瓶中有多少储备溶液，例如 4000 uL）\n"
    )
    st.markdown(
        " **警告**：请确保此处输入的信息正确无误。"
    )

    # Template vial file upload
    st.file_uploader(
        "您可以在此上传模板样品瓶文件（例如从之前的运行中导出）：",
        type=["csv"],
        key="vial_df_template",
        accept_multiple_files=False,
    )
    if st.session_state["vial_df_template"] is not None:
        initialise_or_update_VialDF()
        try:
            st.session_state["platform_backend"].session_container["VialDF"].df = (
                pd.read_csv(st.session_state["vial_df_template"])
            )
            backend.session_container.update_session(
                "number_of_vials",
                len(
                    st.session_state["platform_backend"]
                    .session_container["VialDF"]
                    .df.index
                ),
            )
        except Exception as error:
            st.error(str(error))

    # Number of Vials input and update
    sample_col1, sample_col2 = st.columns([4, 1])
    number_vials = sample_col2.number_input(
        "样品瓶数量",
        min_value=1,
        max_value=100,
        value=backend.session_container.get("number_of_vials", 1),
    )
    backend.session_container.update_session("number_of_vials", number_vials)

    # Display and load the vials
    handle_vials()


def create_simple_widget(
    label: str, param_type: Any, default: Any = None, key=None, value: Any = None
):
    default_or_value = value if value is not None else default

    if param_type == bool:
        return st.checkbox(label, value=default_or_value, key=key)
    elif param_type == int:
        return st.number_input(
            label,
            value=default_or_value if default_or_value is not None else 0,
            key=key,
        )
    elif param_type == float:
        return st.number_input(
            label,
            value=default_or_value if default_or_value is not None else 0.0,
            key=key,
        )
    elif param_type == str:
        return st.text_input(
            label,
            value=default_or_value if default_or_value is not None else "",
            key=key,
        )
    elif param_type == list:
        return st.text_area(
            label, value=str(default_or_value) if default_or_value else "", key=key
        )
    else:
        st.write(f"参数 `{label}` 不支持的类型: {param_type}")
        return default_or_value


def create_input_widget(parameter: LamaParameter, full_path: str):
    st.write(full_path)

    param_type = parameter.type
    param_name = parameter.name
    default = parameter.default
    value = parameter.value

    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin is Literal:
        # Handle Literal types
        options = list(args)
        option_of_value = options.index(value) if value in options else 0
        selected = st.selectbox(
            label=param_name,
            options=options,
            index=option_of_value,
            key=f"{full_path}/{param_name}",
        )
        return selected

    elif origin is tuple or origin is Tuple:
        # Handle Tuple types
        if len(args) == 2 and args[1] == Ellipsis:
            # Variable-length Tuple, e.g., Tuple[int, ...]
            element_type = args[0]
            num_elements = st.number_input(
                f"{param_name} 的元素个数",
                min_value=1,
                max_value=10,
                value=3,
                step=1,
                key=f"{full_path}/{param_name}",
            )
            elements = []
            for i in range(num_elements):
                elem = create_simple_widget(
                    f"{param_name} [{i + 1}]",
                    element_type,
                    value=(
                        value[i]
                        if isinstance(value, tuple) and i < len(value)
                        else None
                    ),
                    default=(
                        default[i]
                        if isinstance(default, tuple) and i < len(default)
                        else None
                    ),
                    key=f"{full_path}/{param_name}/{i}",
                )
                elements.append(elem)
            return tuple(elements)
        else:
            # Fixed-length Tuple
            elements = []
            for i, elem_type in enumerate(args):
                elem = create_simple_widget(
                    f"{param_name} [{i + 1}]",
                    elem_type,
                    value=(
                        value[i]
                        if isinstance(value, tuple) and i < len(value)
                        else None
                    ),
                    default=(
                        default[i]
                        if isinstance(default, tuple) and i < len(default)
                        else None
                    ),
                    key=f"{full_path}/{param_name}/{i}",
                )
                elements.append(elem)
            return tuple(elements)
    # elif origin is list or origin is List:
    elif origin is list or origin is List:
        # Handle List types
        element_type = args[0] if args else Any  # Get the type of elements in the list
        if get_origin(element_type) is Literal:
            # Handle List of Literal types
            options = list(get_args(element_type))
            default_selected = value if isinstance(default, list) else default
            selected = st.multiselect(
                label=param_name,
                options=options,
                default=default_selected,
                key=f"{full_path}/{param_name}",
            )
            parameter.value = selected
            return selected
        else:
            # Handle List of other types
            # For simplicity, use a text area where users can input comma-separated values
            input_str = st.text_area(
                label=param_name,
                value=(
                    ",".join(map(str, value))
                    if isinstance(value, list)
                    else ",".join(map(str, default))
                ),
                key=f"{full_path}/{param_name}",
            )
            # Split the input string into a list based on commas
            input_list = [item.strip() for item in input_str.split(",") if item.strip()]
            parameter.value = input_list
            return input_list

    else:
        return create_simple_widget(
            param_name,
            param_type,
            default,
            value=value,
            key=f"{full_path}/{param_name}",
        )


def traverse_methods(
    methods: List[LamaMethod], parent_path: str = ""
) -> List[Dict[str, Any]]:
    flat_methods = []
    for method in methods:
        current_path = (
            f"{parent_path}/{method.method_name}" if parent_path else method.method_name
        )
        flat_methods.append({"method": method, "full_path": current_path})
        # Traverse submethods recursively
        if method._submethods:
            flat_methods.extend(traverse_methods(method._submethods, current_path))
    return flat_methods


def serialize_method(method: LamaMethod, parent_path: str = ""):
    current_path = (
        f"{parent_path}/{method.method_name}" if parent_path else method.method_name
    )
    for param in method._parameters:
        key = f"{current_path}/{param.name}"
        if key in st.session_state:
            param.value = st.session_state[key]
    # Serialize submethods
    for submethod in method._submethods:
        serialize_method(submethod, current_path)

    # Handle other_parameters if needed


def display_ml_task_all_settings(chemical_parameters: list[ML_parameter]):
    """here we just need to display the parameter to search for tasks as we will generate candidates for all"""
    # first find if there is a parameter that has the attribute task parameter set to true,
    # if more than one pick the first and set all others to false
    task_param = None
    for chem in chemical_parameters:
        if chem.task_feature:
            task_param = chem.name
            break
    for chem in chemical_parameters:
        if chem.name != task_param:
            chem.task_feature = False

    ml_task = st.selectbox(
        "选择用于设置任务的条件参数",
        [chem.name for chem in chemical_parameters],
        index=(
            [chem.name for chem in chemical_parameters].index(task_param)
            if task_param is not None
            else 0
        ),
        key="task_param",
    )
    chemical_of_interest = [
        chem for chem in chemical_parameters if chem.name == ml_task
    ][0]
    chemical_of_interest.task_feature = True
    # make sure that no other chemical has the task value set to true and if they have task value removed
    for chem in chemical_parameters:
        if chem != chemical_of_interest:
            chem.task_feature = False
            if hasattr(chem, "task_value"):
                del chem.task_value


def display_ml_task_settings(chemical_parameters: list[ML_parameter]):
    """Display the task settings for the chemical parameter, the user needs to choose which parameter
    is the multi task based on and then choose the feature to generate candidates for"""
    # first find if there is a parameter that has the attribute task parameter set to true,
    # if more than one pick the first and set all others to false
    task_param = None
    for chem in chemical_parameters:
        if chem.task_feature:
            task_param = chem.name
            break
    for chem in chemical_parameters:
        if chem.name != task_param:
            chem.task_feature = False

    ml_task = st.selectbox(
        "选择要设为目标任务的 ML 参数",
        [chem.name for chem in chemical_parameters],
        index=(
            [chem.name for chem in chemical_parameters].index(task_param)
            if task_param is not None
            else 0
        ),
        key="task_param",
    )
    chemical_of_interest = [
        chem for chem in chemical_parameters if chem.name == ml_task
    ][0]
    chemical_of_interest.task_feature = True
    task_feature = st.selectbox(
        "选择要生成候选方案的特征",
        chemical_of_interest.discrete,
        index=(
            chemical_of_interest.discrete.index(chemical_of_interest.task_value)
            if hasattr(chemical_of_interest, "task_value")
            else 0
        ),
        key="task_value",
    )

    chemical_of_interest.task_value = task_feature
    # make sure that no other chemical has the task value set to true and if they have task value removed
    for chem in chemical_parameters:
        if chem != chemical_of_interest:
            chem.task_feature = False
            if hasattr(chem, "task_value"):
                del chem.task_value
