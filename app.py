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

from core.ollama_client import check_ollama_status
from core import rag_engine
from generators import plantuml_gen, graphviz_gen, doc_generator, analysis
from utils.plantuml_renderer import render_to_bytesio, get_diagram_url


# ═══════════════════════════════════════════════════════════════
#  Custom CSS
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    /* Dark-themed stat cards */
    .stat-card {
        background: linear-gradient(135deg, #1e1e2f 0%, #2d2d44 100%);
        border: 1px solid #3a3a5c;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 10px;
    }
    .stat-card h2 {
        font-size: 2rem;
        margin: 0;
        background: linear-gradient(90deg, #7c3aed, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stat-card p { color: #94a3b8; margin: 4px 0 0 0; font-size: 0.85rem; }
    /* Status badge */
    .badge-ok   { color:#4ade80; font-weight:600; }
    .badge-err  { color:#f87171; font-weight:600; }
    /* Section divider */
    .section-divider { border-top: 1px solid #334155; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("# 🔍 RAG Visualizer")
    st.caption("Powered by DeepSeek Coder + Ollama")
    st.markdown("---")

    # Ollama status check
    status = check_ollama_status()
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
    if rag_engine.get_project_path():
        stats = rag_engine.get_project_stats()
        overview = analysis.get_overview(stats)
        st.metric("Indexed Chunks", overview["total_chunks"])
        st.metric("Total Classes", overview["total_classes"])
        st.metric("Files Parsed", overview["total_files"])


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
        "- 📐 UML class/sequence/activity diagrams\n"
        "- 📖 AI-powered documentation\n"
        "- 💬 Interactive project Q&A"
    )
    st.stop()

# ── Gather stats ──
stats = rag_engine.get_project_stats()
overview = analysis.get_overview(stats)

tab_overview, tab_class, tab_deps, tab_activity, tab_docs, tab_chat = st.tabs([
    "📊 Overview",
    "📐 Class Diagram",
    "🔗 Dependency Graph",
    "🗺️ Activity Diagram",
    "📖 Documentation",
    "💬 Chat",
])


# ── Tab 1: Overview ─────────────────────────────────────────
with tab_overview:
    st.markdown("## Project Overview")

    # Stat cards row
    cols = st.columns(6)
    card_data = [
        (overview["total_files"],   "Files Parsed"),
        (overview["total_chunks"],  "Chunks Indexed"),
        (overview["total_classes"], "Classes"),
        (overview["java_files"],    "Java Files"),
        (overview["kotlin_files"],  "Kotlin Files"),
        (overview["xml_files"],     "XML Files"),
    ]
    for col, (val, label) in zip(cols, card_data):
        with col:
            st.markdown(
                f'<div class="stat-card"><h2>{val}</h2><p>{label}</p></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # Architecture pattern
    arch = analysis.detect_architecture_pattern(stats)
    st.markdown(f"### 🏗️ Architecture Pattern\n**{arch}**")

    # Component breakdown
    col_type, col_layer = st.columns(2)
    with col_type:
        st.markdown("#### By Component Type")
        for ctype, count in sorted(overview["components_by_type"].items(),
                                   key=lambda x: -x[1]):
            st.markdown(f"- **{ctype}**: {count}")
    with col_layer:
        st.markdown("#### By Layer")
        for layer, count in sorted(overview["components_by_layer"].items(),
                                   key=lambda x: -x[1]):
            st.markdown(f"- **{layer}**: {count}")

    # Manifest & Gradle info
    manifest = analysis.get_manifest_info()
    gradle = analysis.get_gradle_info()

    if manifest:
        st.markdown('<div class="section-divider"></div>',
                    unsafe_allow_html=True)
        st.markdown("### 📋 Manifest Info")
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            st.markdown(f"**Package:** `{manifest.get('package', 'N/A')}`")
            st.markdown(f"**Min SDK:** {manifest.get('min_sdk', 'N/A')}")
            st.markdown(f"**Target SDK:** {manifest.get('target_sdk', 'N/A')}")
        with mcol2:
            if manifest.get("permissions"):
                st.markdown("**Permissions:**")
                for p in manifest["permissions"][:10]:
                    short = p.split(".")[-1]
                    st.markdown(f"- `{short}`")

    if gradle and gradle.get("dependencies"):
        st.markdown('<div class="section-divider"></div>',
                    unsafe_allow_html=True)
        with st.expander("📦 Gradle Dependencies", expanded=False):
            for dep in gradle["dependencies"]:
                st.code(dep, language=None)


# ── Tab 2: Class Diagram ────────────────────────────────────
with tab_class:
    st.markdown("## PlantUML Class Diagram")

    class_names = analysis.get_class_list(stats)
    focus = st.selectbox(
        "Focus on class (optional — leave blank for full project):",
        ["(All Classes)"] + class_names,
        key="class_focus",
    )
    diagram_type = st.radio(
        "Diagram type:", ["Class Diagram", "Sequence Diagram"],
        horizontal=True, key="uml_type",
    )

    if st.button("🎨 Generate Diagram", key="gen_uml"):
        with st.spinner("Generating via RAG + DeepSeek Coder…"):
            fc = None if focus == "(All Classes)" else focus
            if diagram_type == "Class Diagram":
                puml = plantuml_gen.generate_class_diagram(fc)
            else:
                puml = plantuml_gen.generate_sequence_diagram(fc)

        # ── Render the diagram as an image ──
        st.markdown("### 📊 Rendered Diagram")
        with st.spinner("Rendering diagram image…"):
            img = render_to_bytesio(puml)
        if img:
            st.image(img, caption=f"{diagram_type}", use_container_width=True)
            # Download rendered PNG
            img.seek(0)
            st.download_button(
                "🖼️ Download PNG", img.read(),
                file_name="diagram.png", mime="image/png", key="dl_uml_png",
            )
        else:
            st.warning("Could not render image. Check the PlantUML syntax below.")

        # ── Show raw PlantUML code in expander ──
        with st.expander("📝 View PlantUML Source Code", expanded=False):
            st.code(puml, language="plantuml")
        st.download_button("💾 Download .puml", puml,
                           file_name="diagram.puml", mime="text/plain", key="dl_uml_puml")


# ── Tab 3: Dependency Graph ─────────────────────────────────
with tab_deps:
    st.markdown("## Dependency Graph")

    dep_mode = st.radio(
        "Graph type:",
        ["Layer Overview (deterministic)", "AI-Enhanced Dependencies"],
        horizontal=True, key="dep_mode",
    )

    focus_dep = None
    if dep_mode == "AI-Enhanced Dependencies":
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


# ── Tab 4: Activity Diagram ─────────────────────────────────
with tab_activity:
    st.markdown("## Activity / Navigation Flow Diagram")
    st.caption("Uses RAG to retrieve all UI components and generate a navigation flow.")

    if st.button("🗺️ Generate Activity Diagram", key="gen_activity"):
        with st.spinner("Generating navigation flow diagram…"):
            puml = plantuml_gen.generate_activity_diagram()

        # ── Render the diagram as an image ──
        st.markdown("### 📊 Rendered Activity Diagram")
        with st.spinner("Rendering diagram image…"):
            img = render_to_bytesio(puml)
        if img:
            st.image(img, caption="Activity / Navigation Flow", use_container_width=True)
            img.seek(0)
            st.download_button(
                "🖼️ Download PNG", img.read(),
                file_name="activity_diagram.png", mime="image/png", key="dl_act_png",
            )
        else:
            st.warning("Could not render image. Check the PlantUML syntax below.")

        # ── Show raw PlantUML code in expander ──
        with st.expander("📝 View PlantUML Source Code", expanded=False):
            st.code(puml, language="plantuml")
        st.download_button("💾 Download .puml", puml,
                           file_name="activity_diagram.puml", mime="text/plain", key="dl_act_puml")


# ── Tab 5: Documentation ────────────────────────────────────
with tab_docs:
    st.markdown("## AI-Generated Documentation")

    doc_mode = st.radio(
        "Mode:", ["Single Section", "Full Report"],
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
        if st.button("📖 Generate Full Report", key="gen_full_report"):
            progress = st.progress(0, text="Starting…")

            step_count = [0]

            def _doc_progress(msg):
                step_count[0] += 1
                progress.progress(
                    min(step_count[0] / len(doc_generator.SECTIONS), 1.0),
                    text=msg,
                )

            with st.spinner("Generating full report…"):
                report = doc_generator.generate_full_report(
                    progress_callback=_doc_progress
                )
            progress.progress(1.0, text="Done!")
            st.markdown(report)
            st.download_button(
                "💾 Download Report (.md)", report,
                file_name="project_documentation.md", mime="text/markdown",
            )


# ── Tab 6: Chat ─────────────────────────────────────────────
with tab_chat:
    st.markdown("## 💬 Ask About Your Project")
    st.caption(
        "Ask any question — RAG retrieves the most relevant code chunks "
        "and DeepSeek Coder answers based on your actual codebase."
    )

    # Chat history in session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    user_q = st.chat_input("Ask a question about your project…")
    if user_q:
        st.session_state.chat_history.append(
            {"role": "user", "content": user_q}
        )
        with st.chat_message("user"):
            st.markdown(user_q)

        with st.chat_message("assistant"):
            response_area = st.empty()
            full_response = ""
            for token in rag_engine.query_stream(user_q):
                full_response += token
                response_area.markdown(full_response + "▌")
            response_area.markdown(full_response)

        st.session_state.chat_history.append(
            {"role": "assistant", "content": full_response}
        )
