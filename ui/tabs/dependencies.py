import streamlit as st
from generators import graphviz_gen
from core import rag_engine
from generators import analysis
from ui.sidebar import _cached_ollama_status
import config

def render():
    """Renders the Dependency Graph tab."""
    st.markdown("## Dependency Graph")

    dep_mode = st.radio(
        "Graph type:",
        ["Layer Overview (deterministic)", "AI-Enhanced Dependencies"],
        horizontal=True, key="dep_mode",
    )

    focus_dep = None
    if dep_mode == "AI-Enhanced Dependencies":
        stats = rag_engine.get_project_stats()
        focus_dep_sel = st.selectbox(
            "Focus class (optional):",
            ["(All)"] + analysis.get_class_list(stats),
            key="dep_focus",
        )
        focus_dep = None if focus_dep_sel == "(All)" else focus_dep_sel

    with st.popover("🔗 Generate Graph"):
        status = _cached_ollama_status()
        models = status.get("models", [])
        if not models:
            models = [config.LLM_MODEL]
        
        default_model = getattr(config, "MODEL_ROUTING", {}).get("dependency_graph", config.LLM_MODEL)
        idx = models.index(default_model) if default_model in models else 0
        selected_model = st.selectbox("LLM Model:", models, index=idx, key="dep_mod")
        
        if st.button("Confirm Generate", key="gen_dep_btn"):
            st.session_state["do_gen_dep"] = selected_model

    if st.session_state.get("do_gen_dep"):
        selected_model = st.session_state.pop("do_gen_dep")
        with st.spinner(f"Building dependency graph ({selected_model})…"):
            if dep_mode == "Layer Overview (deterministic)":
                dot_code = graphviz_gen.generate_layer_graph()
            else:
                dot_code = graphviz_gen.generate_dependency_graph(focus_dep, target_model=selected_model)

        st.markdown("### Graphviz DOT Output")
        try:
            st.graphviz_chart(dot_code)
        except Exception:
            st.warning("Could not render inline. Showing raw DOT code:")
        st.code(dot_code, language="dot")
        st.download_button("💾 Download .dot", dot_code,
                           file_name="dependency.dot", mime="text/plain")
