"""
Android Project Visualizer — Streamlit App
===========================================
Analyze Android projects with RAG + DeepSeek Coder 6.7B.

Run:  streamlit run app.py
"""

import sys, os

# ── Ensure project root is on sys.path ──────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Must be the FIRST Streamlit call
st.set_page_config(
    page_title="Android Project Visualizer",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core import rag_engine
from ui import styles, sidebar
from ui.tabs import overview, uml, dependencies, security, docs, chat, history

# ═══════════════════════════════════════════════════════════════
#  Initialization & Layout
# ═══════════════════════════════════════════════════════════════

# Load custom CSS
styles.load_css()

# Render sidebar
project_path, analyze_btn = sidebar.render_sidebar()

# ═══════════════════════════════════════════════════════════════
#  Initialization & Session State
# ═══════════════════════════════════════════════════════════════

if "active_project" not in st.session_state:
    st.session_state.active_project = None

if "resume_project" in st.session_state:
    project_path = st.session_state.resume_project
    analyze_btn = True
    del st.session_state.resume_project

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
            st.session_state.active_project = project_path
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

if not st.session_state.active_project:
    # ── Hero welcome section ──
    st.markdown(
        '<div class="hero-container">'
        '<div class="hero-title">Android Project Visualizer</div>'
        '<div class="hero-subtitle">'
        'Analyze your Android codebase with AI-powered insights. '
        'Generate diagrams, detect vulnerabilities, explore dependencies, '
        'and chat with your code — all powered by local LLMs.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Feature cards ──
    cols = st.columns(4)
    features = [
        ("📐", "Diagrams", "Generate class, sequence, activity, and more diagrams automatically"),
        ("🔗", "Dependencies", "Visualize project structure and dependency graphs"),
        ("🛡️", "Code Quality", "AI security audit with severity-ranked findings"),
        ("💬", "Chat", "Ask questions about your codebase with RAG-powered answers"),
    ]
    for col, (icon, title, desc) in zip(cols, features):
        with col:
            st.markdown(
                f'<div class="feature-card">'
                f'<span class="feature-icon">{icon}</span>'
                f'<div class="feature-title">{title}</div>'
                f'<div class="feature-desc">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("")
    st.markdown(
        "👉 Enter an Android project path in the sidebar and click "
        "**Analyze Project** to get started."
    )
    st.markdown("---")
    history.render()
    st.stop()


tab_overview, tab_uml, tab_deps, tab_security, tab_docs, tab_chat, tab_history = st.tabs([
    "📊 Overview",
    "📐 Diagrams",
    "🔗 Dependency Graph",
    "🛡️ Code Quality",
    "📖 Documentation",
    "💬 Chat",
    "🕒 History",
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

with tab_history:
    history.render()
