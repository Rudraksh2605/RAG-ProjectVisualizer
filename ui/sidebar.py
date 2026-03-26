import streamlit as st
from core.ollama_client import check_ollama_status
from core import rag_engine
from generators import analysis

@st.cache_data(ttl=30)
def _cached_ollama_status():
    return check_ollama_status()

def render_sidebar():
    """Renders the left sidebar for configuration and status."""
    with st.sidebar:
        st.markdown("# 🤖 Android Visualizer")
        st.markdown(
            '<div class="powered-by">Powered by <strong>DeepSeek Coder</strong> + <strong>Ollama</strong></div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # Ollama status check (cached — avoids HTTP call on every re-render)
        status = _cached_ollama_status()
        if status["ok"]:
            st.markdown('<span class="badge-ok">● Ollama Online</span>',
                        unsafe_allow_html=True)
            st.caption(f"Models: {', '.join(status['models'][:5])}")
        else:
            st.markdown('<span class="badge-err">● Ollama Offline</span>',
                        unsafe_allow_html=True)
            st.error(f"Error: {status['error']}")
            st.info("Start Ollama and reload the page.")

        st.markdown("---")

        # Project path input
        project_path = st.text_input(
            "📂 Project Path",
            placeholder=r"D:\path\to\your\android\project",
            help="Absolute path to the root of an Android project.",
        )

        analyze_btn = st.button("🚀 Analyze Project", type="primary",
                                use_container_width=True,
                                disabled=not project_path)

        st.markdown("---")

        # Show indexing stats if available
        if st.session_state.get("active_project") and rag_engine.get_project_path() == st.session_state["active_project"]:
            stats = rag_engine.get_project_stats()
            overview = analysis.get_overview(stats)
            st.markdown(
                f'<div class="sidebar-stat"><span class="label">Indexed Chunks</span>'
                f'<span class="value">{overview["total_chunks"]}</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="sidebar-stat"><span class="label">Total Classes</span>'
                f'<span class="value">{overview["total_classes"]}</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="sidebar-stat"><span class="label">Files Parsed</span>'
                f'<span class="value">{overview["total_files"]}</span></div>',
                unsafe_allow_html=True,
            )
            
        return project_path, analyze_btn
