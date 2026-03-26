import streamlit as st
import os
from utils import history_manager

def render():
    st.markdown(
        '<div class="section-header">'
        '<span class="icon">🕒</span>'
        '<span class="title">Recent Projects</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    projects = history_manager.get_all_projects()

    if not projects:
        st.info("No projects analyzed yet. Go to the sidebar to analyze your first project.")
        return

    # Render a list or simple cards for each project
    for info in projects:
        path = info["path"]
        stats = info.get("stats", {})
        dt = info.get("last_accessed", "").replace("T", " ")[:16]  # simplified date format

        st.markdown(
            f'<div class="project-card"></div>',
            unsafe_allow_html=True,
        )
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{os.path.basename(path)}**")
                st.caption(f"{path}")
            with col2:
                items = stats.get('total_files', 0)
                chunks = stats.get('total_chunks', 0)
                st.markdown(f"Files: **{items}** | Chunks: **{chunks}**")
                st.caption(f"Last accessed: {dt}")
            with col3:
                if st.button("Resume", key=f"resume_{path}"):
                    st.session_state.resume_project = path
                    st.rerun()
            st.divider()
