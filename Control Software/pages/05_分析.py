""" 实验设置

运行 'streamlit run robochem.py' 后此文件自动激活。
在此填写运行平台所需的所有额外参数。

Author: Elia Savino
"""

import streamlit as st
import copy

from backend.platform_backend import PlatformBackend
from backend.frontend_functions import (
    page_header,
    render_analytical_parameter,
    create_input_widget,
    traverse_methods,
    ensure_backend,
)

# --------------------------------------------- Streamlit 页面设置 ---------------------------------------------------
backend: PlatformBackend = ensure_backend()
page_header()

# ------------------------------------------------- 分析方法 ------------------------------------------------
st.subheader("分析")
st.write("")
st.markdown(
    "请在下方指定优化过程中使用的分析参数。"
)

analytics1, analytics2 = st.columns([1, 1])
if "HITL" not in backend.session_container.get("experiment_type", ""):
    available_analytics_names = backend.get_analytics()
    if available_analytics_names != []:
        analysis_techique = analytics1.selectbox(
            "选择分析技术",
            available_analytics_names,
            key="analysis_type",
            index=(
                list(available_analytics_names).index(
                    backend.session_container.get("analysis_type", None)
                )
                if backend.session_container.get("analysis_type", None)
                else 0
            ),
        )

        backend.session_container.update_session("analysis_type", analysis_techique)

    analytic_parameters = backend.get_analytic_parameters()
    if analytic_parameters == None:
        st.error(
            "当前实验不支持此分析技术，出现问题。"
        )
    elif len(analytic_parameters) == 0:
        st.write(
            "您正在使用人机协作（HITL）技术，无需进一步选择！"
        )
    else:
        required_parameters, optional_parameters, maths_available = analytic_parameters

        maths = analytics2.selectbox(
            "选择分析的数学方法",
            maths_available,
            key="analysis_maths",
            index=(
                list(maths_available).index(
                    backend.session_container.get("analysis_maths", None)
                )
                if backend.session_container.get("analysis_maths", None)
                and backend.session_container.get("analysis_maths", None)
                in maths_available
                else 0
            ),
        )
        backend.session_container.update_session("analysis_maths", maths)

        # 首先移除会话容器中存在但不在必需参数或可选参数中的参数
        analytical_parameters_in_sesh = backend.session_container.search_by_tag(
            "analytical_parameter"
        )

        # 筛选出匹配 analytical_maths 标签的可选参数
        optional_params = [
            param for param in optional_parameters if param.tag in (maths, "all")
        ]
        required_parameters = [
            param for param in required_parameters if param.tag in (maths, "all")
        ]

        # 合并必需和可选参数
        merged_params = copy.deepcopy(required_parameters + optional_params)
        merged_param_names = {param.name for param in merged_params}

        # 移除不在合并列表中的分析参数
        for analytical_param in analytical_parameters_in_sesh:
            if analytical_param not in merged_param_names:
                del backend.session_container[analytical_param]

        # 处理合并后的参数
        for parameter in merged_params:
            if parameter.name not in backend.session_container:
                parameter_data = backend.analytical_parameter(
                    name=parameter.name,
                    min_value=parameter.min_value,
                    max_value=parameter.max_value,
                    unit=parameter.units,
                    omni_tag=parameter.tag,
                    value=parameter.value,
                    allowed_values=parameter.discrete_values,
                )
                parameter_data.value = parameter.value
            else:
                parameter_data = backend.session_container[parameter.name]

            render_analytical_parameter(parameter.name, parameter_data)
            backend.session_container.update_session(parameter.name, parameter_data)


else:
    backend.session_container["analysis_type"] = "Human"
    st.success(
        "您正在使用人机协作（HITL）技术，无需进一步选择！"
    )
