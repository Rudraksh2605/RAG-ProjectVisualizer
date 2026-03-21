"""
Graphviz DOT dependency graph generator — uses RAG to retrieve
dependency relationships and asks DeepSeek Coder to produce
semantically-labelled DOT syntax.
"""

from core import rag_engine


def generate_dependency_graph(focus_class: str = None, target_model: str = None) -> str:
    """
    Generate a Graphviz DOT dependency graph.
    """
    question = (
        f"Generate a Graphviz DOT dependency graph centered on '{focus_class}' "
        f"showing all classes it depends on, classes that depend on it, and any "
        f"Dependency Injection (Dagger/Hilt/Koin) bindings involved. "
        f"Label each edge with the relationship type."
        if focus_class
        else "Generate a Graphviz DOT dependency graph showing the main "
             "components of this project, their dependencies, and the Dependency Injection "
             "(Dagger/Hilt/Koin) architecture connecting them. "
             "Label edges with relationship types (extends, implements, "
             "uses, injects, provides). Group nodes by architectural layer or DI module."
    )
    raw = rag_engine.query(question, analysis_type="dependency_graph", top_k=12, target_model=target_model)
    return _extract_dot(raw)


def generate_layer_graph() -> str:
    """
    Generate a Graphviz graph grouped by architectural layers.
    """
    stats = rag_engine.get_project_stats()
    classes = stats.get("classes", [])

    # Build a deterministic layer graph from parsed metadata
    layers = {"UI": [], "Business Logic": [], "Data": [], "Service": [],
              "DI": [], "Other": []}
    for cls in classes:
        ly = cls.get("layer", "Other")
        if ly not in layers:
            ly = "Other"
        layers[ly].append(cls["name"])

    lines = [
        'digraph ProjectLayers {',
        '  rankdir=TB;',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10];',
        '',
    ]

    colors = {
        "UI": "#4FC3F7",
        "Business Logic": "#81C784",
        "Data": "#FFB74D",
        "Service": "#CE93D8",
        "DI": "#F48FB1",
        "Other": "#E0E0E0",
    }

    for layer, names in layers.items():
        if not names:
            continue
        safe = layer.replace(" ", "_")
        color = colors.get(layer, "#E0E0E0")
        lines.append(f'  subgraph cluster_{safe} {{')
        lines.append(f'    label="{layer}";')
        lines.append(f'    style=filled; color="{color}30"; fontname="Helvetica Bold";')
        for n in names:
            sn = _safe(n)
            lines.append(f'    {sn} [label="{n}", fillcolor="{color}"];')
        lines.append('  }')
        lines.append('')

    lines.append('}')
    return "\n".join(lines)


def _extract_dot(text: str) -> str:
    """Extract DOT syntax from LLM output."""
    # Try to find digraph block
    if "digraph" in text:
        start = text.index("digraph")
        # Find the matching closing brace
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    # Try code fences
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            body = parts[1].strip()
            for prefix in ("dot", "graphviz"):
                if body.startswith(prefix):
                    body = body[len(prefix):].strip()
            if "digraph" in body or "graph" in body:
                return body

    # Fallback: wrap
    return f'digraph G {{\n  rankdir=TB;\n  {text.strip()}\n}}'


def _safe(name: str) -> str:
    """Make a name safe for DOT identifiers."""
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)
