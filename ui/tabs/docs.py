import streamlit as st
from generators import doc_generator
from ui.sidebar import _cached_ollama_status
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
        with st.popover("📝 Generate Section"):
            status = _cached_ollama_status()
            models = status.get("models", [])
            if not models:
                models = [config.LLM_MODEL]
            
            default_model = config.LLM_MODEL
            idx = models.index(default_model) if default_model in models else 0
            selected_model = st.selectbox("LLM Model:", models, index=idx, key="doc_single_mod")
            
            if st.button("Confirm Generate", key="gen_doc_single_btn"):
                st.session_state["do_gen_doc_single"] = selected_model
        
        if st.session_state.get("do_gen_doc_single"):
            selected_model = st.session_state.pop("do_gen_doc_single")
            with st.spinner(f"Generating {selected_title} ({selected_model})…"):
                content = doc_generator.generate_section(
                    sec_options[selected_title], target_model=selected_model
                )
            st.markdown(content)
    else:
        st.caption(
            f"All {len(doc_generator.SECTIONS)} sections will be generated "
            f"concurrently using **{config.PARALLEL_MAX_WORKERS} threads**."
        )
        with st.popover("📖 Generate Full Report"):
            status = _cached_ollama_status()
            models = status.get("models", [])
            if not models:
                models = [config.LLM_MODEL]
            selected_model_batch = st.selectbox("LLM Model (for all):", models, key="doc_batch_mod")
            if st.button("Confirm Full Report", key="gen_doc_batch_btn"):
                st.session_state["do_gen_doc_batch"] = selected_model_batch
                
        if st.session_state.get("do_gen_doc_batch"):
            selected_model = st.session_state.pop("do_gen_doc_batch")
            progress = st.progress(0, text=f"Starting parallel generation ({selected_model})…")

            step_count = [0]

            def _doc_progress(msg):
                step_count[0] += 1
                progress.progress(
                    min(step_count[0] / len(doc_generator.SECTIONS), 1.0),
                    text=msg,
                )

            with st.spinner("Generating full report in parallel…"):
                report = doc_generator.generate_full_report(
                    progress_callback=_doc_progress, target_model=selected_model
                )
            progress.progress(1.0, text="✅ Done!")
            st.markdown(report)
            st.download_button(
                "💾 Download Report (.md)", report,
                file_name="project_documentation.md", mime="text/markdown",
            )
