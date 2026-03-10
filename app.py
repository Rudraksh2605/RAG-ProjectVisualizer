"""
RAG-ProjectVisualizer — Streamlit App
======================================
Analyze Android projects with RAG + DeepSeek Coder 6.7B.

Run:  streamlit run app.py
"""

import sys, os

# ── Ensure project root is on sys.path ──────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Must be the FIRST Streamlit call
st.set_page_config(
    page_title="RAG Project Visualizer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core import rag_engine
from ui import styles, sidebar
from ui.tabs import overview, uml, dependencies, security, docs, chat

# ═══════════════════════════════════════════════════════════════
#  Initialization & Layout
# ═══════════════════════════════════════════════════════════════

# Load custom CSS
styles.load_css()

# Render sidebar
project_path, analyze_btn = sidebar.render_sidebar()

# ═══════════════════════════════════════════════════════════════
#  Indexing
# ═══════════════════════════════════════════════════════════════

if analyze_btn and project_path:
    if not os.path.isdir(project_path):
        st.error(f"Directory not found: {project_path}")
    else:
        progress_bar = st.progress(0, text="Starting analysis…")
        status_text = st.empty()

        step = [0]

        def _progress(msg: str):
            step[0] += 1
            frac = min(step[0] / 8, 1.0)
            progress_bar.progress(frac, text=msg)
            status_text.caption(msg)

        try:
            idx_stats = rag_engine.index_project(project_path, progress=_progress)
            progress_bar.progress(1.0, text="Done!")
            st.success(
                f"Indexed **{idx_stats['chunks']}** chunks from "
                f"**{idx_stats['parsed']}** files."
            )
            st.rerun()         # Refresh sidebar stats
        except Exception as e:
            st.error(f"Indexing failed: {e}")

# ═══════════════════════════════════════════════════════════════
#  Main tabs (only shown after indexing)
# ═══════════════════════════════════════════════════════════════

if not rag_engine.get_project_path():
    st.markdown("## 👋 Welcome to RAG Project Visualizer")
    st.markdown(
        "Enter an Android project path in the sidebar and click "
        "**Analyze Project** to get started."
    )
    st.markdown(
        "This tool uses **RAG** (Retrieval-Augmented Generation) with "
        "**DeepSeek Coder 6.7B** to analyze your codebase and generate:\n"
        "- 📊 Dependency graphs\n"
        "- 📐 UML class/sequence/activity/state/component/use-case/package/deployment diagrams\n"
        "- 🛡️ Security & Code Smell scanning\n"
        "- 📖 AI-powered documentation\n"
        "- 💬 Interactive project Q&A\n"
        "- ⚡ Parallel batch generation with threading"
    )
    st.stop()


tab_overview, tab_uml, tab_deps, tab_security, tab_docs, tab_chat = st.tabs([
    "📊 Overview",
    "📐 UML Diagrams",
    "🔗 Dependency Graph",
    "🛡️ Code Quality",
    "📖 Documentation",
    "💬 Chat",
])

with tab_overview:
    overview.render()

with tab_uml:
    uml.render()

with tab_deps:
    dependencies.render()

with tab_security:
    security.render()

with tab_docs:
    docs.render()

with tab_chat:
    chat.render()
