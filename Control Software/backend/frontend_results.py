"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr:

"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from backend.frontend_functions import handle_stock_solutions
from backend.frontend_functions import (
    handle_vials,
    display_sample_and_stock_solution_ui,
)
from backend.platform_backend import PlatformBackend
from omniplatypus.procedures.unit_tasks.user_actions import (
    UserActionRequest,
    UserAction,
    UserSetSamplesRequest,
    UserSetSamples,
)


# from pygmo import hypervolume


def calculate_hypervolume(results_df: pd.DataFrame, objectives: list):
    """Function to calculate the hypervolume of a pareto front

    Args:
    results_df: the results df
    objectives: the objectives list

    Returns:
    the hypervolume
    """
    # get the objectives values
    obj_values = -results_df[objectives].values
    # find the ref point, then for each point calculate the hypervolume
    ref_point = obj_values.max(axis=0) + 0.1
    hvs = []
    # iterate through each row and calculate hypervolume
    for i in range(len(results_df)):
        hv = hypervolume(obj_values[i, :].reshape(1, -1))
        hvs.append(hv.compute(ref_point))
    return hvs


def plot_results(results_df: pd.DataFrame, objectives: list):
    """This needs to plot either 1 or two plots, depending on the number of objectives
    if there's one objective we want a scatter plot of objective vs experiment number
    if there's two objectives we want a scatter plot of both objectives vs experiment number and a
    scatter plot of objective 1 vs objective 2 (pareto plot)
    if there are more than two objectives we want a scatter plot of each objective vs experiment number and a
    selector to choose which two objectives to plot against each other

    :param results_df: the results datafarame
    :param objectives: the objectives list (column names of the results_df)
    """
    # Style plots for streamlit
    plt.style.use("dark_background")
    plt.rcParams["figure.facecolor"] = "#0e1117"
    plt.rcParams["axes.facecolor"] = "#0e1117"
    plt.rcParams["savefig.facecolor"] = "#0e1117"
    # 中文字体配置:必须在 style.use 之后设置(否则会被样式重置覆盖)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    num_obj = len(objectives)
    exp_n = results_df.index
    cmap = plt.get_cmap("Pastel1")
    colors = [cmap(i) for i in np.linspace(0, 1, num_obj)]

    obvsex, obvsob = st.columns(2)
    with obvsex:
        fig, ax = plt.subplots()
        for i, obj in enumerate(objectives):
            ax.scatter(
                exp_n,
                results_df[obj],
                label=obj,
                color=colors[i],
                s=50,
                marker="o",
                alpha=0.8,
            )
            # if the results_df has the obj_variance column add the STD to the plot
            if f"{obj}_variance" in results_df.columns:
                # ax.fill_between(
                #     exp_n,
                #     results_df[obj] - results_df[f"{obj}_variance"]**0.5,
                #     results_df[obj] + results_df[f"{obj}_variance"]**0.5,
                #     color=colors[i],
                #     alpha=0.2,
                # )
                ax.errorbar(
                    exp_n,
                    results_df[obj],
                    yerr=results_df[f"{obj}_variance"] ** 0.5,
                    fmt="o",
                    color=colors[i],
                    alpha=0.3,
                )
        fig.suptitle("目标值 vs 实验迭代次数")
        ax.set_xlabel("实验编号")
        ax.set_ylabel("目标值")
        ax.legend()
        ax.set_xlim(-1, len(exp_n))
        ax.set_xticks(exp_n)

        st.pyplot(fig)
    if num_obj == 2:
        with obvsob:
            fig, ax = plt.subplots()
            fig.suptitle(
                f"目标 {objectives[0]} 与 {objectives[1]} 的帕累托图"
            )
            ax.scatter(
                results_df[objectives[0]],
                results_df[objectives[1]],
                color="darkviolet",
                edgecolor="violet",
                s=50,
                marker="s",
                alpha=0.8,
            )
            ax.plot(
                results_df[objectives[0]],
                results_df[objectives[1]],
                color="violet",
                alpha=0.5,
                linestyle="--",
            )
            ax.set_xlabel(objectives[0])
            ax.set_ylabel(objectives[1])
            st.pyplot(fig)

    elif num_obj > 2:
        obj1 = st.selectbox("选择第一个目标", options=objectives)
        obj2 = st.selectbox("选择第二个目标", options=objectives)
        with obvsob:
            fig, ax = plt.subplots()
            fig.suptitle(f"目标 {obj1} 与 {obj2} 的帕累托图")
            ax.scatter(
                results_df[obj1],
                results_df[obj2],
                color="purple",
                edgecolor="black",
                s=50,
                marker="s",
                alpha=0.8,
            )
            ax.plot(
                results_df[obj1],
                results_df[obj2],
                color="purple",
                alpha=0.5,
                linestyle="--",
            )
            ax.set_xlabel(obj1)
            ax.set_ylabel(obj2)
            st.pyplot(fig)


def handle_vials_empty(backend: PlatformBackend, error: UserActionRequest):
    """Function to handle when a vial is empty:
    this should display the vials DF and the Stock DF and let the user modify them
    :param backend: the backend object
    :param error: the data platform object (i.e. the vials DF)
    """
    # get the columns of the merge df:
    returned_df = backend.unmerge_df(error.error_data)

    # update the vials df with the returned df:
    backend.session_container["VialDF"].update_from_df(returned_df)
    # slice the data platform to get the vials df

    # first we display the stock solutions:
    stock_col1, stock_col2 = st.columns([3, 1])
    number_stocks = stock_col2.number_input(
        "储备溶液数量",
        min_value=1,
        max_value=100,
        key="number_of_stock_solutions",
        value=st.session_state["platform_backend"].session_container.get(
            "number_of_stock_solutions", 1
        ),
    )
    st.session_state["platform_backend"].session_container.update_session(
        "number_of_stock_solutions", number_stocks
    )
    # display and load the stock solutions
    handle_stock_solutions(stock_col1)

    # now we display the vials df
    st.write("## 管理样品瓶")
    st.write(
        "建议：移除空瓶和样品，补充溶剂，必要时添加新的储备溶液"
        "\n 注意：浓度可能会变化！"
    )
    sample_col1, sample_col2 = st.columns([4, 1])
    number_vials = sample_col2.number_input(
        "样品瓶数量",
        min_value=1,
        max_value=100,
        value=st.session_state["platform_backend"].session_container.get(
            "number_of_vials", 1
        ),
    )
    st.session_state["platform_backend"].session_container.update_session(
        "number_of_vials", number_vials
    )

    # display and load the vials:
    handle_vials()

    with st.button("重新填充"):
        merge_df = backend.merge_df()
        resolved = UserAction(
            error_keyword="VialsEmpty",
            error_resolution_data=merge_df,
            error_id=error.error_id,
            error_resolution_keyword="update samples",
        )
        backend.platform_experiment.submit_user_action(resolved)
        backend.session_container["pushed_status"] = True


def handle_results(
    backend: PlatformBackend = None,
):
    """Function to handle the results from the platform

    Args:
    visual_queue: the queue with the results
    backend: the backend object
    hitl_queue: the queue to send the HITL results back to the platform
    """
    # get the results df:
    # check if there is data in the visual queue:
    visual_data = backend.ml_experiment_class.get_visual()
    if visual_data is not None and not isinstance(visual_data, str):
        visual_data = visual_data.drop_duplicates(subset=["run_index"], keep="last")
        backend.session_container["results_df"] = visual_data
    elif backend.session_container.get("stopped", False) or (
        isinstance(visual_data, str) and visual_data == "stop"
    ):
        # kill the ML thread:
        backend.session_container["stopped"] = True
        backend.ml_experiment_class.kill_thread()
        st.success(
            f"您的实验已完成！建议现在保存会话！\n"
            f"您也可以继续添加更多实验！",
            icon=":material/sentiment_very_satisfied:",
        )
        cols = st.columns([1, 1, 1], vertical_alignment="bottom")
        more_exp = cols[1].number_input(
            "额外实验数量", min_value=1, value=1
        )
        if cols[2].button("添加更多实验"):
            st.write(f"Adding {more_exp} experiments")
            backend.ml_experiment_class.add_more_experiments(more_exp)
            backend.session_container["stopped"] = False

    # st.write(backend.ml_experiment_class.results_df)
    # get the objective columns
    objectives = backend.session_container["objectives"]

    # display the results (editable if HITL)
    st.write("## 结果")
    st.markdown(
        "实验结果将在此显示，如果您正在进行人机协作（HITL）实验，请在测量完成后"
        '添加结果，然后点击"提交结果"按钮。\n\n'
        "**注意**：此列表每30秒更新一次。"
    )
    if "results_df" not in backend.session_container:
        st.write("暂无结果")
        return
    # display the results DF

    res_df = st.data_editor(
        backend.session_container["results_df"],
        column_config={obj: st.column_config.NumberColumn() for obj in objectives},
        num_rows="dynamic",
    )

    if hasattr(backend.ml_experiment_class, "put_HITL"):
        # validate the DF:
        if not backend.ml_experiment_class.res_df_is_valid(res_df):
            st.warning("请填写所有目标值")
        elif st.button("提交结果"):
            backend.session_container["results_df"] = res_df
            print(res_df)
            backend.ml_experiment_class.put_HITL(res_df)
            backend.session_container["pushed_results"] = True

    else:
        backend.session_container["results_df"] = res_df

    # plot the results
    if hasattr(backend.ml_experiment_class, "utilities_df"):
        # add a collapse to show the utilities df
        with st.expander("Utilities DF", expanded=False):
            st.data_editor(
                backend.ml_experiment_class.utilities_df,
                disabled=True,
            )

    st.write("## 结果图表")
    plot_results(backend.session_container["results_df"], objectives)


def check_platform_status(
    backend: PlatformBackend,
) -> None:
    """
    Checkas and handles platform status updates, such as requests to manually fix an issue or changes in the samples.

    @param backend: PlatformBackend
        The backend connected to the platform.
    """

    # Load the latest samples information
    platform_samples = None
    while True:
        latest_samples = backend.platform_experiment.get_samples(block=False)
        if latest_samples is not None:
            platform_samples = latest_samples
        else:
            break
    if platform_samples is not None:
        backend.session_container["VialDF"].update_from_platform(platform_samples)
        st.success("样品已更新。")

    # Check if an error condition is already present.
    action_request = backend.session_container.get("platform_error_condition", None)
    if action_request is None:
        action_request = backend.platform_experiment.get_action_requests(block=False)
        # store the error so in 30s when the function is run again it still exists.
        backend.session_container["platform_error_condition"] = action_request
    if action_request is None:
        return
    action_request: UserActionRequest
    action_request_type = type(action_request)

    # Check the type of user request
    if action_request_type is UserSetSamplesRequest:
        # Problem with the samples dataframe...
        action_request: UserSetSamplesRequest

        st.error(
            f"**{action_request_type.__name__}**\n\n"
            f"平台遇到可用样品问题：\n\n"
            f"{action_request.description}",
            icon=":material/oil_barrel:",
        )
        backend.session_container["VialDF"].update_from_platform(action_request.samples)

        display_sample_and_stock_solution_ui()

        def send_solution():
            new_platform_df = backend.merge_dfs()
            solution = UserSetSamples(new_samples=new_platform_df)
            backend.platform_experiment.submit_user_action(solution, block=False)
            backend.session_container["platform_error_condition"] = None

        st.write("\n")
        st.button(
            "修复",
            on_click=send_solution,
            help="将修改后的样品数据框发送到平台。",
        )
    else:
        st.error(
            f"**{action_request_type.__name__}**\n\n"
            f"平台遇到问题：\n\n"
            f"{action_request.description}\n\n"
            "*目前尚无处理此问题的实现方式。请联系开发人员。*",
            icon=":material/error:",
        )


@st.fragment(run_every="20min")
def save_periodically():
    """saves session periodically"""
    # print("saving_sesh")
    bknd = st.session_state["platform_backend"]

    bknd.session_container.save_session()


@st.fragment(run_every="30s")
def main_results():
    """Main function to display the results of the platform

    first we get our hands on the backend and all the queues.
    the queues are:
    - The platform queue, which communicates the results from the platform to the ML
    - The ML queue, which communicates the experiments to the platform
    - The platform status queue, which communicates the status of the platform to the Frontend
    - The platform returns queue, which communicates messages from the frontend to the platform
    - The visual queue: which puts results from ML to the frontend
    - The HITL queue (which is only present in HITL experiments) which communicates the HITL results to the platform

    Queue gets:

    platform status queue: this status queue will have dictionaries with the structure
            {status: "status_name", data: data}
        where status_name can be:
        - "vials_empty": volumes in the vials are either not sufficient, or the sample vials are all full.
            the data will be the vials DF with all the info

        - "error": an error has occurred, the data will be the error message

    visual queue: the visual queue will have results DFs that will be displayed in the frontend, which for HITL purposes
            the DF will have shape:
            [exp_n, param1, param2, param3, param4, vial_number, vial_location, objective, objective, objective]
            the vial info will be returned only if the collector is in use.
            This side needs to take the df, display it (and let the user edit for HITL methods)
            and also plot the results


    Queue puts:

    platform returns queue: this queue will have the modified DFs that will be sent back to the platform
                {status:'refill", data: df}


    HITL queue: in this queue the frontend will put the results df once the user clicks push results
                {status: "results", data: df}


    """

    # Get the backend and queues
    backend = st.session_state["platform_backend"]
    # before gathering the queue check if the backend has them, otherwise throw an error

    # check if there are messages in the platform status queue
    # get data from platform status:

    check_platform_status(backend)

    # make some space on the page
    st.write("")
    st.write("")
    st.write("")

    # check if there are messages in the visual queue

    handle_results(backend)
