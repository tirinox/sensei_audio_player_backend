import streamlit as st
import subprocess
import threading

# Initialize session state variables once
if "make_running" not in st.session_state:
    st.session_state.make_running = False
if "make_output" not in st.session_state:
    st.session_state.make_output = ""
if "make_target" not in st.session_state:
    st.session_state.make_target = ""


def run_command_simple(command):
    """Run command and return output"""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout


def run_make_command(target: str):
    st.session_state.make_running = True
    st.session_state.make_output = f"Running: make {target}\n\n"
    st.session_state.make_target = target

    process = subprocess.Popen(
        ["make", target],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        st.session_state.make_output += line
        st.rerun()  # triggers screen refresh to show output live

    process.wait()
    st.session_state.make_running = False
    st.rerun()


def display_make_button(button_name, target):
    # Disable button while command is running
    if st.button(button_name, disabled=st.session_state.get("make_running")):
        threading.Thread(target=run_make_command, args=(target,)).start()

    # Spinner and live output
    if st.session_state.make_running:
        with st.spinner(f"Running make {st.session_state.make_target}..."):
            st.code(st.session_state.make_output, language="bash")
    elif st.session_state.make_output:
        st.success(f"make {st.session_state.make_target} finished")
        st.code(st.session_state.make_output, language="bash")


def display_make_button_simple(command, button_label="Run Command"):
    if st.button(button_label):
        with st.spinner("Running command..."):
            output = run_command_simple(command)
        st.code(output, language="bash")
