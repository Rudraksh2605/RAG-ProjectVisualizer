"""
AI-powered documentation generator.
Each documentation section issues its own targeted RAG query
with the appropriate analysis_type and optional layer filter.

Supports parallel generation of all sections via ThreadPoolExecutor.
"""

import re
from typing import Dict
from core import rag_engine
from utils.parallel import run_parallel
import config


def _strip_duplicate_title(content: str, title: str) -> str:
    """Remove the leading heading from LLM content if it duplicates the section title.

    The LLM often starts its response with a heading like ``### 📋 Project Overview``
    even though we already wrap the section with ``## 📋 Project Overview``.  This
    helper strips the first heading line when it is a near-duplicate of *title*.
    """
    # Strip the emoji prefix for comparison (e.g. "📋 " -> "Project Overview")
    plain_title = re.sub(r'^[^\w]*', '', title).strip().lower()
    lines = content.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Check if the first non-empty line is a markdown heading
        if stripped.startswith('#'):
            heading_text = stripped.lstrip('#').strip()
            plain_heading = re.sub(r'^[^\w]*', '', heading_text).strip().lower()
            if plain_title and plain_heading and (
                plain_title in plain_heading or plain_heading in plain_title
            ):
                # Remove this duplicate heading line
                lines.pop(i)
                return '\n'.join(lines).strip()
        break  # first non-empty line isn't a heading, nothing to strip
    return content


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


def _make_section_task(key, title, atype, layer):
    """Create a closure that generates one section (for parallel execution)."""
    def _task():
        question = f"Generate the '{title}' documentation section for this project."
        return rag_engine.query(
            question,
            analysis_type=atype,
            top_k=10,
            layer_filter=layer,
        )
    return _task


def generate_all_sections(progress_callback=None) -> Dict[str, str]:
    """
    Generate ALL documentation sections in parallel and return them as
    {section_key: markdown_content}.
    """
    tasks = [
        (key, _make_section_task(key, title, atype, layer))
        for key, title, atype, layer in SECTIONS
    ]

    results = run_parallel(
        tasks,
        max_workers=config.PARALLEL_MAX_WORKERS,
        progress_callback=progress_callback,
    )
    return results


def generate_full_report(progress_callback=None) -> str:
    """
    Generate a single Markdown document with all sections (in parallel).
    """
    sections = generate_all_sections(progress_callback)
    parts = ["# 📖 Project Documentation\n"]
    for key, title, _, _ in SECTIONS:
        content = sections.get(key, "")
        content = _strip_duplicate_title(content, title)
        parts.append(f"## {title}\n\n{content}\n")
    return "\n---\n\n".join(parts)
