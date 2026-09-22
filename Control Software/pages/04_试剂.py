""" 试剂设置

运行 'streamlit run robochem.py' 后此文件自动激活。

在此填写不同试剂及其对应类型。类型用于在下一页设置机器学习模型（贝叶斯优化）的变量空间，
化学信息存储在电子表格中。

Author: Elia Savino
"""

import pandas as pd
import streamlit as st
from backend.frontend_functions import (
    page_header,
    display_chemical_inputs,
    display_sample_and_stock_solution_ui,
    ensure_backend,
)
from backend.platform_backend import PlatformBackend

# --------------------------------------------- Streamlit 页面设置 ---------------------------------------------------
backend: PlatformBackend = ensure_backend()
page_header()

# --------------------------------------------- 试剂与溶剂 --------------------------------------------------
st.subheader("试剂与溶剂")

st.markdown(
    "指定优化所需的所有化学物质，包括试剂和溶剂。"
)
text_columns = st.columns([0.75, 1])
text_columns[0].markdown(
    "##### 标识符\n"
    "添加唯一标识符，将每种化学物质的名称与已知化学物质匹配。"
    "标识符可指向您的实验日志（Internal_ID）或标准化标识符，如 CAS 编号。"
)
text_columns[1].markdown(
    "##### 用途\n"
    "每种试剂在反应中分配一个角色。\n\n"
    "- 具有相同角色的试剂将被视为可互相替代，"
    " ML 算法在优化轮次中可以交换使用。\n"
    "- 必须至少有一种限制试剂。\n"
)
st.write("\n\n\n")

columns = st.columns([2, 2, 1])
# 试剂数量
number_reagents = columns[0].number_input(
    label="实验中使用的化学物质数量（试剂和溶剂）：",
    min_value=1,
    value=backend.session_container.get("number_of_reagents", 1),
    step=1,
    help="请确保在此添加所有化学物质",
    key="number_of_reagents",
)
backend.session_container.update_session("number_of_reagents", number_reagents)

# 价格
price = columns[2].selectbox(
    "是否添加试剂价格？",
    ["是", "否"],
    key="price",
    index=["是", "否"].index(backend.session_container.get("price", "否")) if backend.session_container.get("price", "否") in ["是", "否"] else 1,
)
st.session_state["platform_backend"].session_container.update_session("price", price)

existing_chemical_keys = backend.session_container.search_by_tag("chemical_parameter")

# 首先显示已有化学物质的输入，并检查修改
for key in existing_chemical_keys:
    chemical = backend.session_container.get(key)
    display_chemical_inputs(
        chemical, existing_chemical_keys.index(key)
    )
    if chemical.name == key and chemical:
        backend.session_container.update_session(key, chemical)
    elif chemical:
        backend.session_container.update_session(chemical.name, chemical)
        del st.session_state["platform_backend"].session_container[key]
    elif not chemical.name:
        del st.session_state["platform_backend"].session_container[key]


# 计算需要额外添加的化学物质数量
num_existing_chemicals = len(existing_chemical_keys)
additional_chemicals_needed = number_reagents - num_existing_chemicals

for i in range(additional_chemicals_needed):
    chemical = st.session_state["platform_backend"].chemical_parameter()
    display_chemical_inputs(chemical, i + num_existing_chemicals)
    if chemical is not None:
        st.session_state["platform_backend"].session_container.update_session(
            chemical.name, chemical
        )
st.markdown("----")

# ------------------------------------------------- 试剂浓度和体积（来自平台模板）------------
display_sample_and_stock_solution_ui()
