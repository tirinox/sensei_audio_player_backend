import streamlit as st

from ui.utils import CommandRunner


def mode_general_tasks():
    st.header("General tasks")

    CommandRunner("uploader").display("make upload", "Upload files")
