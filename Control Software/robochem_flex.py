""" 
Home Page

This is the home page of the streamlit app. By running this from the terminal 'streamlit run robochem_flex.py' the whole app
is started. In this file the session states used in the whole app is initialized. The session states allow the
parameters/values to be saved in between different pages as well as when a button is clicked. (As this normally will
reset all parameters.)

This Page contains the information of how to set up a campaign.

"""

import streamlit as st
import os

from backend.platform_backend import (
    PlatformBackend,
)
from backend.frontend_functions import page_header

# ----------------------! Initialization of the backend !------------------

if "platform_backend" not in st.session_state:
    st.session_state["platform_backend"] = PlatformBackend(st.session_state)

backend = st.session_state["platform_backend"]

# --------------------------------------------- Streamlit page setup ---------------------------------------------------
page_header()


st.subheader("Welcome to the Robochem-Flex platform!")
st.markdown(
    "From here you can setup your optimization campaign, selecting the workflow, exploration space, vials and chemical species involved."
)

st.markdown(
    "If you wish to load a previous campaign, select the 'session.json' file the campaign folder, otherwise select the next page on the left."
    "You can modify and save a campaign at any time, without the need to start it."
    f"By default, your campaign files and results are stored under `{os.path.join(st.session_state['platform_backend'].robochem_path, 'user_name', 'experiment_name')}`. "
)

st.markdown("_____")
st.markdown(
    "Robochem-Flex was brought to you by: S. Pilon, E. Savino, O. M. Bayley, M. Vanzella, M. Claros, P. Siasiaridis,  J. Liu, F. Lukas, M. Damian, V. Tseliou,  N. Intini, A. Slattery, J. San Jose Orduna, T. den Hartog, R. A. H. Peters, A. Gargano, F. Mutti and T. Noël."
)
st.subheader("Happy Optimizing")

st.file_uploader(
    "Upload your session file here",
    type=["json"],
    key="session_file",
    accept_multiple_files=False,
)

if st.session_state["session_file"] is not None:
    ret, error_msg = backend.session_container.load_session(st.session_state["session_file"])
    if ret == "Success":
        st.success("Session Loaded Successfully!")
    elif ret == "Error":
        st.warning(f"Error loading session file: {error_msg}")
        st.info("请检查终端日志获取详细信息，或从零开始配置。")
