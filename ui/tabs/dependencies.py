import streamlit as st
from generators import graphviz_gen
from core import rag_engine
from generators import analysis

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

    if st.button("🔗 Generate Graph", key="gen_dep"):
        with st.spinner("Building dependency graph…"):
            if dep_mode == "Layer Overview (deterministic)":
                dot_code = graphviz_gen.generate_layer_graph()
            else:
                dot_code = graphviz_gen.generate_dependency_graph(focus_dep)

        st.markdown("### Graphviz DOT Output")
        try:
            st.graphviz_chart(dot_code)
        except Exception:
            st.warning("Could not render inline. Showing raw DOT code:")
        st.code(dot_code, language="dot")
        st.download_button("💾 Download .dot", dot_code,
                           file_name="dependency.dot", mime="text/plain")
