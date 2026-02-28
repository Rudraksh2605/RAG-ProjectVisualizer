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

from concurrent.futures import ThreadPoolExecutor
from core.ollama_client import check_ollama_status
from core import rag_engine
from generators import plantuml_gen, graphviz_gen, doc_generator, analysis
from generators import security_scanner
from generators.plantuml_gen import DIAGRAM_REGISTRY
from utils.plantuml_renderer import render_to_bytesio, get_diagram_url
from utils.parallel import run_parallel
import config


# ── Cached helpers (avoid re-running on every Streamlit re-render) ──

@st.cache_data(ttl=30)
def _cached_ollama_status():
    return check_ollama_status()


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
    /* Diagram result card */
    .diagram-card {
        background: #1a1a2e;
        border: 1px solid #3a3a5c;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .diagram-card h4 { color: #a78bfa; margin-bottom: 8px; }
    /* Security severity badges */
    .sev-badge { display: inline-block; padding: 2px 10px; border-radius: 6px;
                 font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; }
    .sev-critical { background: #dc2626; color: #fff; }
    .sev-high { background: #ea580c; color: #fff; }
    .sev-medium { background: #d97706; color: #fff; }
    .sev-low { background: #2563eb; color: #fff; }
    .sev-info { background: #4b5563; color: #e5e7eb; }
    /* Health score card */
    .health-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 2px solid #3b82f6;
        border-radius: 16px;
        padding: 24px;
        text-align: center;
        margin-bottom: 16px;
    }
    .health-card .score { font-size: 3.5rem; font-weight: 800;
        background: linear-gradient(90deg, #4ade80, #22d3ee);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .health-card .grade { font-size: 1.5rem; color: #94a3b8; }
    .health-card .label { color: #64748b; font-size: 0.85rem; margin-top: 4px; }
    /* Finding card */
    .finding-card {
        background: #111827;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .finding-card.sev-border-critical { border-left-color: #dc2626; }
    .finding-card.sev-border-high { border-left-color: #ea580c; }
    .finding-card.sev-border-medium { border-left-color: #d97706; }
    .finding-card.sev-border-low { border-left-color: #2563eb; }
    .finding-card.sev-border-info { border-left-color: #4b5563; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("# 🔍 RAG Visualizer")
    st.caption("Powered by DeepSeek Coder + Ollama")
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
        "- 📐 UML class/sequence/activity/state/component/use-case/package/deployment diagrams\n"
        "- 🛡️ Security & Code Smell scanning\n"
        "- 📖 AI-powered documentation\n"
        "- 💬 Interactive project Q&A\n"
        "- ⚡ Parallel batch generation with threading"
    )
    st.stop()

# ── Gather stats ──
stats = rag_engine.get_project_stats()
overview = analysis.get_overview(stats)

tab_overview, tab_uml, tab_deps, tab_security, tab_docs, tab_chat = st.tabs([
    "📊 Overview",
    "📐 UML Diagrams",
    "🔗 Dependency Graph",
    "🛡️ Code Quality",
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


# ── Tab 2: UML Diagrams (unified) ──────────────────────────
with tab_uml:
    st.markdown("## 📐 UML Diagrams")
    st.caption(
        "Generate 8 types of UML diagrams using RAG + LLM. "
        "Select a single diagram or use **Batch Generate** to create "
        "multiple diagrams in parallel with threading."
    )

    diagram_names = list(DIAGRAM_REGISTRY.keys())
    class_names = analysis.get_class_list(stats)

    # ── Single diagram generation ──
    st.markdown("### 🎯 Single Diagram")
    col_sel, col_focus = st.columns([1, 1])
    with col_sel:
        selected_diagram = st.selectbox(
            "Diagram Type:",
            diagram_names,
            key="uml_type_select",
        )
    with col_focus:
        gen_func, needs_focus = DIAGRAM_REGISTRY[selected_diagram]
        if needs_focus:
            focus_sel = st.selectbox(
                "Focus on class (optional):",
                ["(All Classes)"] + class_names,
                key="uml_focus_class",
            )
        else:
            focus_sel = None
            st.info(f"ℹ️ {selected_diagram} does not use a focus class.")

    if st.button("🎨 Generate Diagram", key="gen_single_uml"):
        with st.spinner(f"Generating {selected_diagram} via RAG + LLM…"):
            if needs_focus and focus_sel and focus_sel != "(All Classes)":
                puml = gen_func(focus_sel)
            elif needs_focus:
                puml = gen_func(None)
            else:
                puml = gen_func()

        # ── Render the diagram as an image ──
        st.markdown(f"### 📊 {selected_diagram}")
        with st.spinner("Rendering diagram image…"):
            img = render_to_bytesio(puml)
        if img:
            st.image(img, caption=selected_diagram, use_container_width=True)
            img.seek(0)
            st.download_button(
                "🖼️ Download PNG", img.read(),
                file_name=f"{selected_diagram.lower().replace(' ', '_')}.png",
                mime="image/png", key="dl_single_png",
            )
        else:
            st.error(
                "⚠️ Could not render the diagram image. The PlantUML syntax "
                "generated by the LLM may contain errors. Check the source "
                "below and try regenerating."
            )

        with st.expander(
            "📝 View PlantUML Source Code",
            expanded=not bool(img),
        ):
            st.code(puml, language="plantuml")
        st.download_button(
            "💾 Download .puml", puml,
            file_name=f"{selected_diagram.lower().replace(' ', '_')}.puml",
            mime="text/plain", key="dl_single_puml",
        )

    # ── Batch diagram generation (parallel) ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("### ⚡ Batch Generate (Parallel)")
    st.caption(
        f"Generate multiple diagrams concurrently using "
        f"**{config.PARALLEL_MAX_WORKERS} worker threads**."
    )

    batch_selected = st.multiselect(
        "Select diagrams to generate:",
        diagram_names,
        default=["Class Diagram", "Component Diagram", "Use Case Diagram"],
        key="batch_select",
    )

    if st.button("🚀 Batch Generate", key="gen_batch_uml",
                 disabled=len(batch_selected) == 0):
        progress = st.progress(0, text="Starting batch generation…")

        step_count = [0]
        total_steps = len(batch_selected)

        def _batch_progress(msg):
            step_count[0] += 1
            progress.progress(
                min(step_count[0] / total_steps, 1.0),
                text=msg,
            )

        # Build tasks — for batch, we skip focus class (use project-wide)
        tasks = []
        for name in batch_selected:
            gen_func, needs_focus = DIAGRAM_REGISTRY[name]
            if needs_focus:
                tasks.append((name, lambda f=gen_func: f(None)))
            else:
                tasks.append((name, gen_func))

        with st.spinner(f"Generating {len(tasks)} diagrams in parallel…"):
            results = run_parallel(
                tasks,
                max_workers=config.PARALLEL_MAX_WORKERS,
                progress_callback=_batch_progress,
            )

        progress.progress(1.0, text="✅ All diagrams generated!")

        # Pre-render all diagrams in parallel (faster than sequential HTTP)
        def _render_one(name_puml):
            name, puml = name_puml
            return name, render_to_bytesio(puml)

        render_pairs = [(n, results[n]) for n in batch_selected if results.get(n)]
        with st.spinner(f"Rendering {len(render_pairs)} diagrams…"):
            with ThreadPoolExecutor(max_workers=4) as pool:
                rendered = dict(pool.map(_render_one, render_pairs))

        # Display each result
        for name in batch_selected:
            puml = results.get(name, "")
            if not puml:
                continue
            st.markdown(f'<div class="diagram-card"><h4>📐 {name}</h4></div>',
                        unsafe_allow_html=True)

            img = rendered.get(name)
            if img:
                st.image(img, caption=name, use_container_width=True)
                img.seek(0)
                safe_name = name.lower().replace(" ", "_")
                st.download_button(
                    f"🖼️ Download {name} PNG", img.read(),
                    file_name=f"{safe_name}.png",
                    mime="image/png", key=f"dl_batch_{safe_name}_png",
                )
            else:
                st.error(
                    f"⚠️ Could not render {name}. The LLM-generated PlantUML "
                    f"may have syntax issues. See source below."
                )

            with st.expander(f"📝 {name} — PlantUML Source", expanded=False):
                st.code(puml, language="plantuml")


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


# ── Tab 4: Security & Code Quality ──────────────────────────
with tab_security:
    st.markdown("## 🛡️ Security & Code Quality Scanner")
    st.caption(
        "AI-powered security audit and code smell detection. "
        "Scans are performed using RAG to retrieve relevant code and the LLM "
        "acts as a senior security auditor."
    )

    scan_mode = st.radio(
        "Scan Mode:",
        ["Single Category", "Full Scan (Parallel ⚡)"],
        horizontal=True, key="scan_mode",
    )

    if scan_mode == "Single Category":
        cat_options = {
            f"{icon} {name}": key
            for key, name, icon, _, _, _, _ in security_scanner.SCAN_CATEGORIES
        }
        selected_cat_display = st.selectbox(
            "Scan Category:",
            list(cat_options.keys()),
            key="scan_cat_select",
        )
        selected_cat_key = cat_options[selected_cat_display]

        # Show category description
        for key, name, icon, desc, _, _, _ in security_scanner.SCAN_CATEGORIES:
            if key == selected_cat_key:
                st.info(f"**{icon} {name}:** {desc}")
                break

        if st.button("🔍 Run Scan", key="run_single_scan"):
            with st.spinner(f"Scanning {selected_cat_display}…"):
                result = security_scanner.scan_category(selected_cat_key)

            if result.get("error"):
                st.error(f"Scan error: {result['error']}")
            else:
                findings = result.get("findings", [])
                if not findings:
                    st.success("No issues found! Your code looks clean. ✅")
                else:
                    st.warning(f"Found **{len(findings)}** issue(s).")
                    for i, f in enumerate(findings, 1):
                        sev = f.get("severity", "INFO")
                        sev_lower = sev.lower()
                        sev_icon = security_scanner.SEVERITY_ICONS.get(sev, "⚪")
                        st.markdown(
                            f'<div class="finding-card sev-border-{sev_lower}">'
                            f'<span class="sev-badge sev-{sev_lower}">{sev}</span> '
                            f'<strong>{sev_icon} {f.get("title", "Untitled")}</strong>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if f.get("location") and f["location"] != "N/A":
                            st.markdown(f"**Location:** `{f['location']}`")
                        if f.get("description"):
                            st.markdown(f"{f['description']}")
                        if f.get("recommendation"):
                            with st.expander("💡 Recommendation", expanded=False):
                                st.markdown(f["recommendation"])
                        st.markdown(
                            '<div class="section-divider"></div>',
                            unsafe_allow_html=True,
                        )

                # Raw response
                with st.expander("📄 Raw LLM Response", expanded=False):
                    st.code(result.get("raw_response", ""), language="json")

    else:
        # Full parallel scan
        st.caption(
            f"All **{len(security_scanner.SCAN_CATEGORIES)}** categories will "
            f"be scanned concurrently using "
            f"**{config.PARALLEL_MAX_WORKERS} threads**."
        )

        # Category picker for full scan
        all_cat_keys = [c[0] for c in security_scanner.SCAN_CATEGORIES]
        all_cat_labels = {
            c[0]: f"{c[2]} {c[1]}" for c in security_scanner.SCAN_CATEGORIES
        }
        selected_cats = st.multiselect(
            "Categories to scan:",
            all_cat_keys,
            default=all_cat_keys,
            format_func=lambda k: all_cat_labels[k],
            key="scan_cats_multi",
        )

        if st.button(
            "🚀 Run Full Scan",
            key="run_full_scan",
            disabled=len(selected_cats) == 0,
        ):
            progress = st.progress(0, text="Starting security scan…")
            step_count = [0]
            total_cats = len(selected_cats)

            def _scan_progress(msg):
                step_count[0] += 1
                progress.progress(
                    min(step_count[0] / total_cats, 1.0),
                    text=msg,
                )

            with st.spinner(
                f"Scanning {total_cats} categories in parallel…"
            ):
                scan_results = security_scanner.scan_all(
                    category_keys=selected_cats,
                    progress_callback=_scan_progress,
                )
            progress.progress(1.0, text="✅ Scan complete!")

            # ── Health Score Dashboard ──
            summary = security_scanner.compute_scan_summary(scan_results)

            st.markdown('<div class="section-divider"></div>',
                        unsafe_allow_html=True)

            score_col, grade_col, findings_col, clean_col = st.columns(4)
            with score_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["health_score"]}</div>'
                    f'<div class="label">Health Score</div></div>',
                    unsafe_allow_html=True,
                )
            with grade_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["health_grade"]}</div>'
                    f'<div class="label">Grade</div></div>',
                    unsafe_allow_html=True,
                )
            with findings_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["total_findings"]}</div>'
                    f'<div class="label">Total Findings</div></div>',
                    unsafe_allow_html=True,
                )
            with clean_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["categories_clean"]}'
                    f'/{summary["categories_scanned"]}</div>'
                    f'<div class="label">Clean Categories</div></div>',
                    unsafe_allow_html=True,
                )

            # ── Severity Breakdown ──
            st.markdown("### Severity Breakdown")
            sev_cols = st.columns(5)
            for col, sev in zip(
                sev_cols,
                ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
            ):
                count = summary["by_severity"].get(sev, 0)
                sev_icon = security_scanner.SEVERITY_ICONS.get(sev, "⚪")
                with col:
                    st.metric(
                        f"{sev_icon} {sev}",
                        count,
                    )

            st.markdown('<div class="section-divider"></div>',
                        unsafe_allow_html=True)

            # ── Per-Category Results ──
            st.markdown("### Detailed Findings")
            for cat in security_scanner.SCAN_CATEGORIES:
                cat_key = cat[0]
                if cat_key not in scan_results:
                    continue
                result = scan_results[cat_key]
                findings = result.get("findings", [])
                error = result.get("error")
                icon = result.get("icon", cat[2])
                display_name = result.get("display_name", cat[1])

                badge = (
                    "✅ Clean" if not findings and not error
                    else f"⚠️ {len(findings)} issue(s)"
                    if findings
                    else f"❌ Error"
                )

                with st.expander(
                    f"{icon} {display_name} — {badge}",
                    expanded=bool(findings),
                ):
                    if error:
                        st.error(f"Scan error: {error}")
                    elif not findings:
                        st.success("No issues detected.")
                    else:
                        for i, f in enumerate(findings, 1):
                            sev = f.get("severity", "INFO")
                            sev_lower = sev.lower()
                            sev_icon_f = security_scanner.SEVERITY_ICONS.get(
                                sev, "⚪"
                            )
                            st.markdown(
                                f'<div class="finding-card '
                                f'sev-border-{sev_lower}">'
                                f'<span class="sev-badge '
                                f'sev-{sev_lower}">{sev}</span> '
                                f'<strong>{sev_icon_f} '
                                f'{f.get("title", "Untitled")}'
                                f'</strong></div>',
                                unsafe_allow_html=True,
                            )
                            if (
                                f.get("location")
                                and f["location"] != "N/A"
                            ):
                                st.markdown(
                                    f"**Location:** `{f['location']}`"
                                )
                            if f.get("description"):
                                st.markdown(f["description"])
                            if f.get("recommendation"):
                                st.caption(
                                    f"💡 **Fix:** {f['recommendation']}"
                                )
                            if i < len(findings):
                                st.markdown("---")

            # ── Download Report ──
            st.markdown('<div class="section-divider"></div>',
                        unsafe_allow_html=True)
            report_md = security_scanner.generate_scan_report(scan_results)
            st.download_button(
                "📥 Download Full Report (.md)",
                report_md,
                file_name="security_scan_report.md",
                mime="text/markdown",
                key="dl_security_report",
            )


# ── Tab 5: Documentation ────────────────────────────────────
with tab_docs:
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


# ── Tab 5: Chat ─────────────────────────────────────────────
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
