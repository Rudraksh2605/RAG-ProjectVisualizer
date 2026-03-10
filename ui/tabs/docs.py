import streamlit as st
from generators import doc_generator
import config

def render():
    """Renders the Documentation tab."""
    st.markdown("## AI-Generated Documentation")

    doc_mode = st.radio(
        "Mode:", ["Single Section", "Full Report (Parallel ⚡)"],
        horizontal=True, key="doc_mode",
    )

    if doc_mode == "Single Section":
        sec_options = {title: key for key, title, _, _ in doc_generator.SECTIONS}
        selected_title = st.selectbox("Section:", list(sec_options.keys()),
                                      key="doc_section")
        if st.button("📝 Generate Section", key="gen_doc_section"):
            with st.spinner(f"Generating {selected_title}…"):
                content = doc_generator.generate_section(
                    sec_options[selected_title]
                )
            st.markdown(content)
    else:
        st.caption(
            f"All {len(doc_generator.SECTIONS)} sections will be generated "
            f"concurrently using **{config.PARALLEL_MAX_WORKERS} threads**."
        )
        if st.button("📖 Generate Full Report", key="gen_full_report"):
            progress = st.progress(0, text="Starting parallel generation…")

            step_count = [0]

            def _doc_progress(msg):
                step_count[0] += 1
                progress.progress(
                    min(step_count[0] / len(doc_generator.SECTIONS), 1.0),
                    text=msg,
                )

            with st.spinner("Generating full report in parallel…"):
                report = doc_generator.generate_full_report(
                    progress_callback=_doc_progress
                )
            progress.progress(1.0, text="✅ Done!")
            st.markdown(report)
            st.download_button(
                "💾 Download Report (.md)", report,
                file_name="project_documentation.md", mime="text/markdown",
            )
