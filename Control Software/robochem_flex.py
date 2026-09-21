""" 
首页

这是 Streamlit 应用的主页面。通过在终端运行 'streamlit run robochem_flex.py' 启动整个应用。
此文件会初始化整个应用中使用的会话状态。会话状态允许参数/值在不同页面之间以及按钮点击后保持
（按钮点击通常会重置所有参数）。

本页面包含如何设置实验活动的信息。

"""

import streamlit as st
import os

from backend.platform_backend import (
    PlatformBackend,
)
from backend.frontend_functions import page_header

# ----------------------! 后端初始化 !------------------

if "platform_backend" not in st.session_state:
    st.session_state["platform_backend"] = PlatformBackend(st.session_state)

backend = st.session_state["platform_backend"]

# --------------------------------------------- Streamlit 页面设置 ---------------------------------------------------
page_header()


st.subheader("欢迎使用 Robochem-Flex 平台！")
st.markdown(
    "在此您可以设置优化活动，选择工作流、探索空间、样品瓶和化学物质。"
)

st.markdown(
    "如需加载之前的实验活动，请选择实验文件夹中的 'session.json' 文件；"
    "否则请点击左侧的下一页。您可以随时修改和保存活动，无需启动它。"
    f"默认情况下，您的活动文件和结果存储在 `{os.path.join(st.session_state['platform_backend'].robochem_path, 'user_name', 'experiment_name')}` 路径下。"
)

st.markdown("_____")
st.markdown(
    "Robochem-Flex 贡献者：S. Pilon, E. Savino, O. M. Bayley, M. Vanzella, M. Claros, P. Siasiaridis,  J. Liu, F. Lukas, M. Damian, V. Tseliou,  N. Intini, A. Slattery, J. San Jose Orduna, T. den Hartog, R. A. H. Peters, A. Gargano, F. Mutti and T. Noël."
)
st.subheader("优化愉快！")

st.file_uploader(
    "上传会话文件",
    type=["json"],
    key="session_file",
    accept_multiple_files=False,
)

if st.session_state["session_file"] is not None:
    ret, error_msg = backend.session_container.load_session(st.session_state["session_file"])
    if ret == "Success":
        st.success("会话加载成功！")
    elif ret == "Error":
        st.warning(f"加载会话文件出错：{error_msg}")
        st.info("请检查终端日志获取详细信息，或从零开始配置。")
