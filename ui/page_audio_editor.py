import os

import streamlit as st

from core.config import AUDIO_SOURCE_PATH
from core.file_man import get_all_codes
from core.indexer import AudioIndexer
from core.segment_man import SegmentManager


def mode_audio_editor():
    # list of codes to select
    st.sidebar.header("Select Code")

    codes = get_all_codes(AUDIO_SOURCE_PATH)
    if not codes:
        st.error("No audio codes found. Please check the AUDIO_SOURCE_PATH configuration.")
        st.stop()

    selected_code = st.sidebar.selectbox("Code", options=codes, help="Select code for audio files database")

    indexer = AudioIndexer.from_code(selected_code)
    files = indexer.get_all_mp3()

    if not files:
        # warning
        st.warning("No audio files found for the selected code.")
        return

    path = os.path.dirname(files[0])
    base_names = [os.path.basename(f) for f in files]

    # Filter files text box
    filter_text = st.sidebar.text_input("Filter files (by name):", "", icon="🔍",
                                        placeholder="Type to filter files...")

    if filter_text:
        base_names = [f for f in base_names if filter_text.lower() in f.lower()]

    selected_audio_file = st.sidebar.selectbox("Audio Files", base_names)
    full_path = os.path.join(path, selected_audio_file)

    st.sidebar.text(f"Full Path: {full_path}")

    if full_path:
        audio_editor_v2(selected_code, full_path)
    else:
        st.header("Select a Code and a File")


def save(seg):
    seg.save()
    st.success("Segments updated and saved successfully!")


def audio_editor_v1(code, filepath):
    # Display the selected code
    st.title(f"Audio Segment Editor")
    st.markdown(f"Code: `{code}`, File path: `{filepath}`")

    st.audio(filepath, format="audio/mp3")

    seg_man = SegmentManager(filepath)
    seg_man.load()

    data = seg_man.sorted_segments
    conv_data = []
    for seg in data:
        item = {
            "start": seg.get('start', 0) / 1000,
            "end": seg.get('end', 0) / 1000,
            "duration": (seg.get('end', 0) - seg.get('start', 0)) / 1000,
            "text": seg.get('text', ''),
        }
        conv_data.append(item)

    # todo: data editor
    event = st.dataframe(
        conv_data,
        selection_mode="multi-row",
        on_select="rerun",
        hide_index=True,
        use_container_width=True,
        column_config={
            "start": st.column_config.NumberColumn(
                "Start (ms)", format="%.2f",
                help="Start time of the segment in seconds",
                width="small",
            ),
            "end": st.column_config.NumberColumn(
                "End (ms)", format="%.2f",
                help="End time of the segment in seconds",
                width="small",
            ),
            "duration": st.column_config.NumberColumn(
                "Duration (s)", format="%.2f",
                help="Duration of the segment in seconds",
                width="small",
            ),
            "text": st.column_config.TextColumn(
                "Text", help="Text associated with the segment",
                # width="medium"
            ),
        }
    )

    st.subheader("Selected members")
    selected_indices = event.selection.rows

    if len(selected_indices) == 1:
        i = selected_indices[0]
        segment = seg_man.sorted_segments[i]
        edit_text = st.text_input("Edit Text", value=segment.get('text', ''))
        if edit_text != segment.get('text', ''):
            seg_man.set_text(i, edit_text)
            save(seg_man)
            st.rerun()

    cannot_join = len(selected_indices) != 2 or abs(selected_indices[0] - selected_indices[1]) != 1
    if st.button("⛙ Join two segments", disabled=cannot_join):
        seg_man.join_segments(selected_indices[0], selected_indices[1])
        save(seg_man)
        st.rerun()

    if st.button("💾 Save"):
        save(seg_man)


def audio_editor_v2(code, filepath):
    # Display the selected code
    st.title(f"Audio Segment Editor")
    st.markdown(f"Code: `{code}`, File path: `{filepath}`")

    st.audio(filepath, format="audio/mp3")

    seg_man = SegmentManager(filepath)
    seg_man.load()

    for i, seg in enumerate(seg_man.sorted_segments):
        time_start = seg.get('start', 0) / 1000
        time_end = seg.get('end', 0) / 1000
        duration = (seg.get('end', 0) - seg.get('start', 0)) / 1000
        text = seg.get('text', '')

        container = st.container(border=True)

        container.markdown(f"**Start:** {time_start:.2f} s, **End:** {time_end:.2f} s, **Duration:** {duration:.2f} s")
        container.checkbox(f"Select Segment #{i + 1}", value=False, key=f"select_{i}")

        new_text = container.text_input(f"Text #{i + 1}", value=text, help="Text associated with the segment",
                                        label_visibility="collapsed")
        if new_text != text:
            seg_man.set_text(i, new_text)
            save(seg_man)

    if st.button("⛙ Join two segments"):
        seg_i_to_join = [
            int(k.split('_')[1]) for k in st.session_state.keys() if k.startswith('select_') and st.session_state[k]
        ]
        st.code(repr(seg_i_to_join))

        cannot_join = len(seg_i_to_join) != 2 or abs(seg_i_to_join[0] - seg_i_to_join[1]) != 1
        if cannot_join:
            st.warning("Please select exactly two consecutive segments to join.")
        else:
            st.info(f"Joining segments {seg_i_to_join[0] + 1} and {seg_i_to_join[1] + 1}...")
            seg_man.join_segments(seg_i_to_join[0], seg_i_to_join[1])
            save(seg_man)
            st.rerun()
