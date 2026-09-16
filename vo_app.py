from datetime import datetime
from pathlib import Path

import streamlit as st

from tts_lib import (
    DEFAULT_RATE,
    VOICES,
    load_scripts,
    save_scripts,
    slugify,
    synthesize,
)

st.set_page_config(
    page_title="Scratch VO",
    page_icon="🎙️",
    layout="centered",
)

if "scripts" not in st.session_state:
    st.session_state.scripts = load_scripts()
if "selected_script_id" not in st.session_state:
    st.session_state.selected_script_id = None
if "generate_script" not in st.session_state:
    st.session_state.generate_script = ""
if "library_title" not in st.session_state:
    st.session_state.library_title = ""
if "library_body" not in st.session_state:
    st.session_state.library_body = ""

pending_generate = st.session_state.pop("pending_generate_script", None)
if pending_generate is not None:
    st.session_state.generate_script = pending_generate

pending_library = st.session_state.pop("pending_library", None)
if pending_library is not None:
    st.session_state.library_title = pending_library.get("title", "")
    st.session_state.library_body = pending_library.get("body", "")

st.title("🎙️ Scratch VO")
st.caption(
    "Paste a script → generate a scratch English voiceover for editing. "
    "Keep drafts in **My Scripts**. Final VO still comes from your boss."
)
st.divider()

if "main_tab" not in st.session_state:
    st.session_state.main_tab = "Generate audio"

pending_tab = st.session_state.pop("pending_main_tab", None)
if pending_tab is not None:
    st.session_state.main_tab = pending_tab

st.radio(
    "Section",
    ["Generate audio", "My Scripts"],
    key="main_tab",
    horizontal=True,
    label_visibility="collapsed",
)

if st.session_state.main_tab == "Generate audio":
    st.text_area(
        "Script",
        key="generate_script",
        height=260,
        placeholder="Paste the English script here…",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        voice_label = st.selectbox("Voice", list(VOICES.keys()))
    with col2:
        rate = st.slider(
            "Speed",
            min_value=-40,
            max_value=40,
            value=DEFAULT_RATE,
            step=5,
            help="0% is the voice default. Negative is slower, positive is faster.",
        )
        st.caption(f"Current rate: **{rate:+d}%**")

    generate_clicked = st.button("🎧 Generate audio", type="primary", use_container_width=True)

    if generate_clicked:
        script = st.session_state.generate_script.strip()
        if not script:
            st.warning("Paste a script first.")
        else:
            with st.spinner("Generating…"):
                try:
                    out_dir = Path("/tmp/scratch-vo")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    filename = f"{slugify(script)}-{datetime.now().strftime('%H%M%S')}.mp3"
                    out_path = out_dir / filename
                    synthesize(script, VOICES[voice_label], rate, out_path)
                    audio_bytes = out_path.read_bytes()
                    st.session_state.last_audio = {
                        "bytes": audio_bytes,
                        "name": filename,
                    }
                    st.success("Done. Play below or save the MP3 for your timeline.")
                except Exception as e:
                    st.error(f"Generation failed: {str(e)[:240]}")

    if st.session_state.get("last_audio"):
        st.audio(st.session_state.last_audio["bytes"], format="audio/mp3")
        st.download_button(
            "💾 Save MP3",
            data=st.session_state.last_audio["bytes"],
            file_name=st.session_state.last_audio["name"],
            mime="audio/mpeg",
            use_container_width=True,
        )

else:
    st.caption("A simple place to keep scripts. Saving here does not generate audio.")

    scripts = st.session_state.scripts
    titles = ["＋ New script"] + [
        s.get("title") or "(untitled)" for s in scripts
    ]
    selected_index = 0
    if st.session_state.selected_script_id:
        for i, s in enumerate(scripts):
            if s["id"] == st.session_state.selected_script_id:
                selected_index = i + 1
                break

    choice = st.selectbox("Saved scripts", titles, index=selected_index)
    if choice == "＋ New script":
        if st.session_state.selected_script_id is not None:
            st.session_state.selected_script_id = None
            st.session_state.pending_library = {"title": "", "body": ""}
            st.rerun()
    else:
        chosen = scripts[titles.index(choice) - 1]
        if st.session_state.selected_script_id != chosen["id"]:
            st.session_state.selected_script_id = chosen["id"]
            st.session_state.pending_library = {
                "title": chosen.get("title", ""),
                "body": chosen.get("body", ""),
            }
            st.rerun()

    st.text_input("Title", key="library_title", placeholder="Episode 12 — intro")
    st.text_area(
        "Script",
        key="library_body",
        height=280,
        placeholder="Keep the latest draft here while the cut keeps changing…",
    )

    b1, b2, b3 = st.columns(3)
    with b1:
        save_clicked = st.button("💾 Save script", type="primary", use_container_width=True)
    with b2:
        use_clicked = st.button("➡️ Use in Generate", use_container_width=True)
    with b3:
        delete_clicked = st.button("🗑️ Delete", use_container_width=True)

    if save_clicked:
        title = st.session_state.library_title.strip()
        body = st.session_state.library_body.strip()
        if not title and not body:
            st.warning("Add a title or some script text before saving.")
        else:
            now = datetime.now().isoformat(timespec="seconds")
            if st.session_state.selected_script_id:
                for s in st.session_state.scripts:
                    if s["id"] == st.session_state.selected_script_id:
                        s["title"] = title or "(untitled)"
                        s["body"] = body
                        s["updated_at"] = now
                        break
            else:
                new_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
                st.session_state.scripts.insert(
                    0,
                    {
                        "id": new_id,
                        "title": title or "(untitled)",
                        "body": body,
                        "updated_at": now,
                    },
                )
                st.session_state.selected_script_id = new_id
            save_scripts(st.session_state.scripts)
            st.success("Saved.")
            st.rerun()

    if use_clicked:
        body = st.session_state.library_body.strip()
        if not body:
            st.warning("This script is empty.")
        else:
            st.session_state.pending_generate_script = body
            st.session_state.pending_main_tab = "Generate audio"
            st.rerun()

    if delete_clicked:
        sid = st.session_state.selected_script_id
        if not sid:
            st.warning("Nothing to delete — this is a new script.")
        else:
            st.session_state.scripts = [
                s for s in st.session_state.scripts if s["id"] != sid
            ]
            save_scripts(st.session_state.scripts)
            st.session_state.selected_script_id = None
            st.session_state.pending_library = {"title": "", "body": ""}
            st.success("Deleted.")
            st.rerun()

st.divider()
st.markdown(
    "<div style='text-align:center; color:gray; font-size:12px'>"
    "Scratch track only · powered by "
    "<a href='https://github.com/rany2/edge-tts' target='_blank'>edge-tts</a>"
    "</div>",
    unsafe_allow_html=True,
)
