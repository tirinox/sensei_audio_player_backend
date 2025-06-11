import subprocess

import streamlit as st


class State:
    @classmethod
    def set_default(cls, key, value):
        """Set default value for a session state key if it doesn't exist"""
        if key not in st.session_state:
            st.session_state[key] = value

    def get(self, key, default=None):
        """Get value from session state with a default fallback"""
        return st.session_state.get(key, default)


class CommandRunner:
    def __init__(self, key: str):
        self.key = key
        self.running_key = f"{key}_running"
        self.output_key = f"{key}_output"
        self.trigger_key = f"{key}_trigger"
        self.command_key = f"{key}_command"

        # Initialize session state
        for k in [self.running_key, self.output_key, self.trigger_key, self.command_key]:
            if k not in st.session_state:
                st.session_state[k] = False if "_running" in k or "_trigger" in k else ""

    def run_command(self, command: str) -> str:
        """Run a shell command and return output"""
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True
        )
        return result.stdout + result.stderr

    def display(self, command: str, label: str = "Run Command"):
        # 1st pass: button clicked
        if st.button(label, disabled=st.session_state[self.running_key]):
            st.session_state[self.trigger_key] = True
            st.session_state[self.command_key] = command
            st.session_state[self.running_key] = True
            st.rerun()

        # 2nd pass: process triggered
        if st.session_state[self.trigger_key]:
            cmd = st.session_state[self.command_key]
            with st.spinner(f"Running: {cmd}"):
                output = self.run_command(cmd)
            st.session_state[self.output_key] = f"$ {cmd}\n\n" + output
            st.session_state[self.trigger_key] = False
            st.session_state[self.running_key] = False
            st.rerun()

        # Show output
        if st.session_state[self.output_key]:
            st.code(st.session_state[self.output_key], language="bash")
