"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr: 物理参数页面，选择哪些参数应保持恒定，哪些应变化

"""

import streamlit as st
from backend.frontend_functions import (
    page_header,
    render_parameter_row,
    render_exp_parameter_row,
    ensure_backend,
)


# --------------------------------------------- Streamlit 页面设置 ---------------------------------------------------
bknd = ensure_backend()
page_header()

st.subheader("物理参数")

st.write("")
required_parameters, required_exp_parameters = bknd.platform_parameters(
    experiment_name=bknd.session_container["platform_experiment"],
    required=True,
    parameter_type="both",
)

for parameter_key, parameter_value in required_parameters.items():
    if parameter_key not in bknd.session_container.keys():
        parameter_data = bknd.physical_parameter(
            name=parameter_key,
            min_value=parameter_value["min_value"],
            max_value=parameter_value["max_value"],
            unit=parameter_value["unit"],
        )
    else:
        parameter_data = bknd.session_container[parameter_key]

    render_parameter_row(parameter_key, parameter_value, parameter_data)

    bknd.session_container.update_session(parameter_key, parameter_data)

for parameter_key, parameter_value in required_exp_parameters.items():
    if parameter_key not in bknd.session_container.keys():
        parameter_data = bknd.experimental_parameter(
            name=parameter_key,
            value=parameter_value["value"],
            allowed_values=parameter_value["allowed_values"],
        )
    else:
        parameter_data = bknd.session_container[parameter_key]

    _ = render_exp_parameter_row(parameter_key, parameter_value, parameter_data)

    bknd.session_container.update_session(parameter_key, parameter_data)

st.write("")
st.write("")
# 添加可选参数的类似表单，仅在用户点击高级复选框时显示


if st.checkbox("高级物理参数"):
    st.write("可选参数")

    optional_parameters = bknd.platform_parameters(
        experiment_name=bknd.session_container["platform_experiment"],
        required=False,
        parameter_type="numerical",
    )
    for parameter_key, parameter_value in optional_parameters.items():
        if parameter_key not in bknd.session_container.keys():
            parameter_data = bknd.physical_parameter(
                name=parameter_key,
                min_value=parameter_value["min_value"],
                max_value=parameter_value["max_value"],
                unit=parameter_value["unit"],
            )
            parameter_data.value = parameter_value["value"]
            parameter_data.style = "constant"
        else:
            parameter_data = bknd.session_container[parameter_key]

        render_parameter_row(
            parameter_key, parameter_value, parameter_data, optional=True
        )

        bknd.session_container.update_session(parameter_key, parameter_data)
else:
    # 从会话容器中移除可选参数
    optional_parameters = bknd.platform_parameters(
        experiment_name=bknd.session_container["platform_experiment"],
        required=False,
        parameter_type="numerical",
    )
    for parameter_key in optional_parameters.keys():
        if (
            parameter_key in bknd.session_container.keys()
            and optional_parameters[parameter_key].get("value")
            == bknd.session_container[parameter_key].value
        ):
            bknd.session_container.pop(parameter_key)

if st.checkbox("高级实验参数"):
    physical_choiches = bknd.platform_parameters(
        experiment_name=bknd.session_container["platform_experiment"],
        required=False,
        parameter_type="non_numerical",
    )

    for parameter_key, parameter_value in physical_choiches.items():
        if parameter_key not in bknd.session_container.keys():
            parameter_data = bknd.experimental_parameter(
                name=parameter_key,
                value=parameter_value["value"],
                allowed_values=parameter_value["allowed_values"],
            )
        else:
            parameter_data = bknd.session_container[parameter_key]

        ret = render_exp_parameter_row(
            parameter_key, parameter_value, parameter_data, optional=True
        )
        if ret == "save":
            bknd.session_container.update_session(parameter_key, parameter_data)

else:
    physical_choiches = bknd.platform_parameters(
        experiment_name=bknd.session_container["platform_experiment"],
        required=False,
        parameter_type="numerical",
    )
    for parameter_key in physical_choiches.keys():
        if (
            parameter_key in bknd.session_container.keys()
            and physical_choiches[parameter_key].get("value")
            == bknd.session_container[parameter_key].value
        ):
            bknd.session_container.pop(parameter_key)
