"""
AI-powered documentation generator.
Each documentation section issues its own targeted RAG query
with the appropriate analysis_type and optional layer filter.
"""

from typing import Dict
from core import rag_engine


# Section definitions: (key, display_title, analysis_type, layer_filter)
SECTIONS = [
    ("overview",     "📋 Project Overview",       "doc_overview",      None),
    ("screens",      "📱 Screens & Navigation",   "doc_screens",       "UI"),
    ("features",     "⚡ Features",                "doc_features",      None),
    ("architecture", "🏗️ Architecture",           "doc_architecture",  None),
    ("tech_stack",   "🔧 Tech Stack",             "doc_tech_stack",    None),
    ("data_flow",    "🔄 Data Flow",              "doc_data_flow",     None),
    ("api",          "🌐 API & Network",          "doc_api",           None),
]


def generate_section(section_key: str) -> str:
    """Generate a single documentation section via RAG."""
    for key, title, atype, layer in SECTIONS:
        if key == section_key:
            question = f"Generate the '{title}' documentation section for this project."
            return rag_engine.query(
                question,
                analysis_type=atype,
                top_k=10,
                layer_filter=layer,
            )
    return "(Unknown section)"


def generate_all_sections(progress_callback=None) -> Dict[str, str]:
    """
    Generate ALL documentation sections and return them as
    {section_key: markdown_content}.
    """
    result = {}
    for i, (key, title, atype, layer) in enumerate(SECTIONS):
        if progress_callback:
            progress_callback(f"Generating {title} ({i + 1}/{len(SECTIONS)})…")
        question = f"Generate the '{title}' documentation section for this project."
        content = rag_engine.query(
            question,
            analysis_type=atype,
            top_k=10,
            layer_filter=layer,
        )
        result[key] = content
    return result


def generate_full_report(progress_callback=None) -> str:
    """
    Generate a single Markdown document with all sections.
    """
    sections = generate_all_sections(progress_callback)
    parts = ["# 📖 Project Documentation\n"]
    for key, title, _, _ in SECTIONS:
        content = sections.get(key, "")
        parts.append(f"## {title}\n\n{content}\n")
    return "\n---\n\n".join(parts)
