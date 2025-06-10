import streamlit as st
from ui.page_audio_editor import mode_audio_editor
from ui.page_general_tasks import mode_general_tasks

# Best practice: set config outside main
st.set_page_config(page_title="Sensei Audio Player Backend UI", layout="wide")

options = [
    "General tasks",
    "Audio Editor",
]


def main():
    st.sidebar.title("Main menu")

    page = st.sidebar.radio("Go to", options)

    if page == options[0]:
        mode_general_tasks()
    else:
        mode_audio_editor()


if __name__ == "__main__":
    main()
