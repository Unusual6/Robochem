""" 运行平台

运行 'streamlit run robochem.py' 后此文件自动激活。

如果所有参数填写正确且所有必要文件位于正确位置，即可运行平台。
页面加载时会生成实验设置文件和空白结果文件。
在"运行平台"页面按下运行按钮即可启动平台。
这将在单独线程中调用 run_optimization_from_gui.py。
优化脚本将创建并更新平台指令文件和结果文件。

在每次运行之间，新的结果将通过读取 figure_hypervolyme.png 和 figure_objectives.png 来显示。

Author: Elia Savino, Simone Pilon
"""

import PIL
import streamlit as st
import numpy as np
import pandas as pd
import asyncio
import os
import json
import time
import subprocess
from os.path import join
from PIL import ImageFile, Image
from backend.frontend_functions import page_header, ensure_backend
from backend.frontend_results import main_results, save_periodically

page_header()
backend = ensure_backend()
# backend 有 4 个可操作的项：
# backend.ready_to_roll 是一个布尔值，决定平台是否具备所有运行所需数据
# backend.rolling 是一个 threading.Event，平台运行时设置（通过 backend.rolling.is_set() 检查）
# backend.frontend_queue 是后端专门用于与前端通信的队列

# --------------------------------------------- 运行平台 -------------------------------------------------#

st.subheader("运行平台")

# 验证数据：
# 如有问题则显示错误消息。
validation_return = backend.validate_data()

st.markdown(
    "在开始实验之前，请使用下方的'保存会话'按钮保存当前设置。\n"
    "数据和日志会自动保存。\n"
)
col_button, col_button_2 = st.columns([1, 1])
with col_button:
    st.empty()
    if st.button("保存会话", help="保存活动设置"):
        ret = backend.session_container.save_session()
        if ret == "Success":
            st.success(
                f"会话已保存至 '{backend.session_container['experiment_path']}'。"
            )
        else:
            st.error(
                f"无法保存会话至 '{backend.session_container['experiment_path']}'。"
            )

st.markdown(
    "\n"
    "使用下方的按钮启动和停止活动。\n\n"
    "**注意：确保平台安全运行：**\n"
    "- **平台内部/周围无人工作。**\n"
    "- **平台盖子已关闭。**\n"
    "- **电源开关已打开。**\n\n"
    "额外检查：\n"
    "- 溶剂储液瓶已满。\n"
    "- 废液桶已空。\n"
    "- 储备溶液已配置（包括反应溶剂、洗涤液和清洗剂）。\n"
    "- 样品瓶隔垫已更换。\n"
)

if not backend.ready_to_roll:
    if validation_return is not None:
        st.error(validation_return)
    else:
        st.error("平台尚未就绪，原因未知。")
else:
    st.checkbox(
        "跳过启动清洗",
        value=False,
        help="初始化平台时不执行初始清洗循环。如果平台上次已正常关机，则无需额外清洗。",
        key="platform_start_skip_cleaning",
    )

    def experiment_shutdown():
        backend.stop()
        ret = backend.session_container.save_session()
        if ret == "Success":
            st.success(
                f"会话已保存至 '{backend.session_container['experiment_path']}'。"
            )
        else:
            st.error(
                f"无法保存会话至 '{backend.session_container['experiment_path']}'。"
            )

    def experiment_pause():
        backend.pause()
        ret = backend.session_container.save_session()
        if ret == "Success":
            st.success(
                f"会话已保存至 '{backend.session_container['experiment_path']}'。"
            )
        else:
            st.error(
                f"无法保存会话至 '{backend.session_container['experiment_path']}'。"
            )

    col_start, col_pause, col_stop, col_emergency_stop = st.columns([1, 1, 1, 1.5])
    start = col_start.button(
        "启动",
        on_click=backend.start,
        disabled=backend.rolling.is_set(),
        help="启动平台并开始实验活动。",
    )
    # pause = col_pause.button(
    #     "Pause",
    #     on_click=backend.pause,
    #     disabled=not backend.rolling.is_set(),
    #     help="Pause the execution of the runs after the current run is over.",
    # )
    stop = col_stop.button(
        "关机",
        on_click=experiment_shutdown,
        disabled=not backend.rolling.is_set(),
        help="当前运行结束后触发关机程序，即使活动尚未完成。",
    )

# main_results 显示结果、错误等所有信息。
if backend.rolling.is_set():
    st.write("平台正在运行")
    main_results()
    save_periodically()
