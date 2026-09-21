""" 用户设置

运行 'streamlit run robochem.py' 后此文件自动激活。

用户可以在此填写用户名（将创建新文件夹，如不存在）和实验名称。
所有相关文件将保存在该位置并以实验名称命名。

Author: Elia Savino
"""

import streamlit as st
import os
from backend.frontend_functions import page_header, ensure_backend


# --------------------------------------------- Streamlit 页面设置 ---------------------------------------------------
backend = ensure_backend()
page_header()

# ----------------------------------------------------- 用户 -----------------------------------------------------------
st.subheader("用户名")
st.write("")

# 创建可用用户列表，将 Guest 文件夹移至最前（默认选项）
available_users = [
    name
    for name in os.listdir(backend.robochem_path)
    if os.path.isdir(os.path.join(backend.robochem_path, name))
]

available_users.insert(0, "Guest")
available_users = list(set(available_users))

col1, col2, col3 = st.columns([10, 2, 10])

# 选择用户
user_name = col1.selectbox(
    "当前用户",
    available_users,
    key="user_name",
    index=available_users.index(backend.session_container.get("user_name", "Guest")),
)
backend.user_path = os.path.join(backend.robochem_path, st.session_state["user_name"])
backend.session_container.update_session("user_name", user_name)

# 如果不在列表中则添加新用户
new_folder = col3.text_input("如果您的名字不在列表中，请在此添加")
if new_folder != "":
    if not os.path.exists(os.path.join(backend.robochem_path, new_folder)):
        os.makedirs(os.path.join(backend.robochem_path, new_folder))
col3.button("更新用户列表")
col2.write("")

st.markdown("_____")

# ------------------------------------------------ 实验名称 ------------------------------------------------------------

st.subheader("实验")
col21, col22 = st.columns([28, 28])
experiment_name = col21.text_input(
    label=f"输入本次实验生成文件的名称：",
    value=backend.session_container.get("experiment_name", ""),
    key="experiment_name",
)
backend.session_container.update_session("experiment_name", experiment_name)

if st.session_state["experiment_name"] != "":
    backend.experiment_path = os.path.join(
        backend.user_path,
        st.session_state["experiment_name"],
    )
    if not os.path.exists(backend.experiment_path):
        os.makedirs(backend.experiment_path)
    backend.session_container.update_session("experiment_path", backend.experiment_path)


st.markdown("_____")
# ------------------------------------------------- 平台选择 -------------------------------------------------

st.subheader("平台与实验选择")
st.write("")
st.write("")
col31, col32, col33 = st.columns([1, 1, 1])
# 选择平台
platform_name = col31.selectbox(
    "选择您使用的平台",
    backend.available_platforms,
    key="platform_name",
    index=(
        backend.available_platforms.index(
            backend.session_container.get("platform_name", None)
        )
        if backend.session_container.get("platform_name", None) is not None
        else 0
    ),
)
backend.session_container.update_session("platform_name", platform_name)
# 查找可用实验：
if platform_name != "":
    available_experiments = backend.platform_available_experiments(platform_name)
else:
    available_experiments = []

platform_experiment = col32.selectbox(
    "选择平台实验类型",
    available_experiments,
    key="platform_experiment",
    index=(
        available_experiments.index(
            backend.session_container.get("platform_experiment", None)
        )
        if backend.session_container.get("platform_experiment", None) is not None
        else 0
    ),
)
backend.session_container.update_session("platform_experiment", platform_experiment)

available_ml = list(backend.ML_classes.keys())

# 选择实验
experiment_name = col33.selectbox(
    "选择实验机器学习方法",
    available_ml,
    key="experiment_type",
    index=(
        available_ml.index(backend.session_container.get("experiment_type", None))
        if backend.session_container.get("experiment_type", None) is not None
        else 0
    ),
)
backend.session_container.update_session("experiment_type", experiment_name)

# 保存选择并初始化实验类

if "experiment_class" in backend.session_container.keys():
    if isinstance(
        backend.session_container["experiment_class"],
        backend.ML_classes[experiment_name],
    ):
        st.success(
            f"已加载 ML 模块，您可能正在继续之前的会话。"
            f" 实验类为 {experiment_name}，不会被覆盖。"
        )
        backend.ml_experiment_class = backend.session_container["experiment_class"]
    else:
        st.warning(
            f"已加载的 ML 模块类型为 {type(backend.session_container['experiment_class'])}，"
            f"与表单中选择的 {experiment_name} 不匹配。是否覆盖并重新开始？"
        )
        if st.button("是"):
            backend.ml_experiment_class = backend.ML_classes[experiment_name]()
            backend.session_container.update_session(
                "experiment_class", backend.ml_experiment_class
            )
elif not hasattr(backend, "ml_experiment_class") or backend.ml_experiment_class is None:
    st.success("未加载 ML 模块，正在初始化新的模块。")
    backend.ml_experiment_class = backend.ML_classes[experiment_name]()
    backend.session_container.update_session(
        "experiment_class", backend.ml_experiment_class
    )
else:
    st.error(
        "实验类出现问题，请重启平台。"
    )
