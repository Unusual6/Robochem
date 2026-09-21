"""机器学习设置

运行 'streamlit run robochem.py' 后此文件自动激活。

在此定义机器学习模型（贝叶斯优化）所需的变量空间。
各类化学参数已在试剂设置页面中确定。对于每种参数类型，设定其边界，即最小值和最大值。

同时决定实验次数，包括初始运行次数和额外优化次数。也可以从之前的运行文件开始优化，
对应的 json 文件需保存在当前活动对应的文件夹中。

Author: Elia Savino
"""

import streamlit as st
import numpy as np
import pandas as pd
from PIL import Image
import os
from os.path import join
from pathlib import Path
from backend.frontend_functions import (
    page_header,
    initialise_ml_parameters,
    display_physical_ml_parameters,
    display_ml_chem_param,
    display_ml_parameters,
    display_ml_task_all_settings,
    display_ml_task_settings,
    ensure_backend,
)

# import custom functions to run these are stored elsewhere to make them easier to unit test


# --------------------------------------------- Streamlit 页面设置 ---------------------------------------------------
page_header()
backend = ensure_backend()
# --------------------------------------------- 机器学习设置 ----------------------------------------------
st.subheader("机器学习设置")

st.markdown("_____")
# --------------------------------------------- 创建变量空间 -------------------------------------------------#

# initialise the ml_params

initialise_ml_parameters()

# get all the Ml parameters
ml_params = backend.session_container.search_by_tag("ML_parameter")
chemical_ml_parameters = [
    backend.session_container[param]
    for param in ml_params
    if backend.session_container[param].phy_chem == "Chemical"
]
physical_ml_parameters = [
    backend.session_container[param]
    for param in ml_params
    if backend.session_container[param].phy_chem == "Physical"
]

st.markdown("## 设置机器学习算法的化学空间")
if len(chemical_ml_parameters) > 0:
    st.markdown("### 化学物质")
    for chemical_ml_param in chemical_ml_parameters:
        display_ml_chem_param(chemical_ml_param)

    if backend.session_container["experiment_type"] in [
        "MultiTaskScope",
        "MultiTaskScope_HITL",
    ]:
        st.markdown("### 任务设置")
        display_ml_task_all_settings(chemical_ml_parameters)
    elif backend.session_container["experiment_type"] == "ScopeAcceleratorTask":
        st.markdown("### 任务设置")
        display_ml_task_settings(chemical_ml_parameters)

if len(physical_ml_parameters) > 0:
    st.markdown("### 物理参数")
    for physical_ml_param in physical_ml_parameters:
        display_physical_ml_parameters(physical_ml_param)


## --------------------------------------------- Decide Objectives -------------------------------------------------#
objectives = (
    "yield",
    "conversion",
    "cost",
    "throughput",
    "selectivity",
    "residence_time",
    "light_power_efficiency",
    "light_power",
    "cost_per_unit_product",
    "mass_balance",
    "Elia-metric",
    "integral_product",
    "integral_sideproduct",
    "enantiomeric excess",
    "diastereomeric ratio",
    "total integral chiral",
)
# objective_index = objectives.index(st.session_state["objective"])
obj = st.multiselect(
    "选择要优化的目标",
    objectives,
    default=(
        backend.session_container["objectives"]
        if "objectives" in backend.session_container
        else objectives[0]
    ),
)
backend.session_container["objectives"] = obj

# --------------------------------------------- Number of runs -------------------------------------------------#
# st.markdown("---")
# load previous data file:
# st.markdown("Load previous data file")
# previous_run_file = st.file_uploader(
#     "Upload your previous data", type=["json"], key="session_file"
# )
# if st.session_state["session_file"] is not None:
#     ret_value = backend.load_previous_experiments(previous_run_file)
#     if ret_value == "Success":
#         st.success("Session Loaded Successfully!")
#     elif ret_value == "Warning":
#         st.warning = "Experimental space does not match, previous run not loaded"
#     elif ret_value == "Error":
#         st.error("Something went terribly wrong, we're all about to die, RUN!")


# display the input parameter for the machine learning model

st.markdown("---")
st.write("## 机器学习参数")
display_ml_parameters()
