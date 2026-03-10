import streamlit as st
from generators import analysis
from core import rag_engine

def render():
    """Renders the Overview tab."""
    st.markdown("## Project Overview")

    # Gather stats
    stats = rag_engine.get_project_stats()
    overview = analysis.get_overview(stats)

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
