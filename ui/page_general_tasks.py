import streamlit as st

from ui.task_make import display_make_button_simple


def mode_general_tasks():
    st.header("General tasks")

    display_make_button_simple("make upload", "Upload")
