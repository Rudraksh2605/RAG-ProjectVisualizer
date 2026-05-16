"""
Graph Builder — populates the Neo4j knowledge graph from parsed files.

Takes the output of tree_sitter_parser (or falls back to the regex
parser data) and creates nodes + relationships in Neo4j.

Called during the indexing pipeline in rag_engine.index_project().
"""

import logging
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

from core import graph_store
from core import tree_sitter_parser
from utils.helpers import detect_android_layer, read_file_safe

log = logging.getLogger("graph_builder")


def build_graph(parsed_files: List[Dict],
                project_path: str,
                progress=None) -> Dict:
    """
    Build the Neo4j knowledge graph from parsed file data.

    Uses tree-sitter for Java/Kotlin files (if available) to extract
    precise AST relationships. Falls back to regex parser data for
    graph construction when tree-sitter is unavailable.

    Returns stats dict: {"nodes_created": int, "relationships_created": int}
    """
    if not graph_store.is_available():
        log.info("Neo4j not available — skipping graph build.")
        return {"nodes_created": 0, "relationships_created": 0}

    if progress:
        progress("Building knowledge graph (clearing old data)…")

    graph_store.clear_graph()

    node_count = 0
    rel_count = 0
    use_treesitter = tree_sitter_parser.is_available()

    if progress:
        progress(f"Extracting graph data from {len(parsed_files)} files…")

    for i, pf in enumerate(parsed_files):
        if pf is None:
            continue

        path = pf.get("path", "")
        lang = pf.get("language", pf.get("type", ""))

        if lang in ("java", "kotlin"):
            if use_treesitter:
                # Use tree-sitter for precise AST extraction
                source = pf.get("source", "")
                graph_data = tree_sitter_parser.extract_graph_data(path, source)
                if graph_data:
                    n, r = _ingest_treesitter_data(graph_data)
                    node_count += n
                    rel_count += r
                    continue

            # Fallback: use regex parser data for graph
            n, r = _ingest_regex_data(pf)
            node_count += n
            rel_count += r

        elif lang in ("manifest", "layout", "gradle"):
            # Create File nodes for config files
            graph_store.upsert_file(path, lang)
            node_count += 1

    # Second pass: resolve cross-file import relationships
    if progress:
        progress("Resolving cross-file relationships…")

    for pf in parsed_files:
        if pf is None:
            continue
        lang = pf.get("language", pf.get("type", ""))
        if lang in ("java", "kotlin"):
            pkg = pf.get("package", "")
            imports = pf.get("imports", [])
            classes = pf.get("classes", [])
            for cls in classes:
                cls_name = cls.get("name", "")
                for imp in imports:
                    graph_store.add_import(cls_name, pkg, imp)
                    rel_count += 1

    if progress:
        progress(f"✅ Knowledge graph: {node_count} nodes, {rel_count} relationships")

    log.info("Graph built: %d nodes, %d relationships", node_count, rel_count)
    return {"nodes_created": node_count, "relationships_created": rel_count}


def _ingest_treesitter_data(graph_data: Dict) -> tuple:
    """Ingest tree-sitter extracted data into Neo4j."""
    node_count = 0
    rel_count = 0

    file_path = graph_data["file_path"]
    language = graph_data["language"]
    package = graph_data.get("package", "")

    # File node
    graph_store.upsert_file(file_path, language)
    node_count += 1

    # Package node
    if package:
        graph_store.upsert_package(package)
        node_count += 1

    for cls in graph_data.get("classes", []):
        cls_name = cls["name"]
        annotations = cls.get("annotations", [])

        # Detect component type and layer using existing heuristics
        superclass = cls.get("superclass", "") or ""
        from core.parser import _detect_component_type
        component_type = _detect_component_type(cls_name, superclass, annotations)
        layer = detect_android_layer(component_type, cls_name, superclass, annotations)

        # Class node
        graph_store.upsert_class(
            name=cls_name,
            package=package,
            file_path=file_path,
            component_type=component_type,
            layer=layer,
            language=language,
            annotations=annotations,
        )
        node_count += 1

        # Inheritance
        if cls.get("superclass"):
            graph_store.add_inheritance(cls_name, package, cls["superclass"])
            rel_count += 1

        # Interfaces
        for iface in cls.get("interfaces", []):
            graph_store.add_interface(cls_name, package, iface)
            rel_count += 1

        # Methods
        for method in cls.get("methods", []):
            method_name = method["name"]
            graph_store.upsert_method(
                cls_name, package, method_name,
                method.get("return_type", "void"),
            )
            node_count += 1

            # Method calls
            for call in method.get("calls", []):
                graph_store.add_method_call(
                    cls_name, package, method_name, call,
                )
                rel_count += 1

        # Fields
        for field in cls.get("fields", []):
            graph_store.upsert_field(
                cls_name, package,
                field["name"], field.get("type", "Object"),
            )
            node_count += 1
            rel_count += 1  # HAS_FIELD + possibly OF_TYPE

    return node_count, rel_count


def _ingest_regex_data(parsed_file: Dict) -> tuple:
    """Fallback: ingest regex-parsed data into Neo4j."""
    node_count = 0
    rel_count = 0

    path = parsed_file.get("path", "")
    lang = parsed_file.get("language", "java")
    pkg = parsed_file.get("package", "")

    # File node
    graph_store.upsert_file(path, lang)
    node_count += 1

    # Package
    if pkg:
        graph_store.upsert_package(pkg)
        node_count += 1

    for cls in parsed_file.get("classes", []):
        cls_name = cls.get("name", "")
        if not cls_name:
            continue

        component_type = cls.get("component_type", "Class")
        layer = cls.get("layer", "Other")
        annotations = cls.get("annotations", [])

        graph_store.upsert_class(
            name=cls_name,
            package=pkg,
            file_path=path,
            component_type=component_type,
            layer=layer,
            language=lang,
            annotations=annotations,
        )
        node_count += 1

        # Inheritance
        if cls.get("superclass"):
            graph_store.add_inheritance(cls_name, pkg, cls["superclass"])
            rel_count += 1

        # Interfaces
        for iface in cls.get("interfaces", []):
            graph_store.add_interface(cls_name, pkg, iface)
            rel_count += 1

    # Methods (from regex parser — less precise but still useful)
    for method in parsed_file.get("methods", []):
        first_class = parsed_file["classes"][0]["name"] if parsed_file.get("classes") else "Unknown"
        graph_store.upsert_method(
            first_class, pkg, method["name"],
            method.get("return_type", "void"),
        )
        node_count += 1

    # Fields
    for field in parsed_file.get("fields", []):
        first_class = parsed_file["classes"][0]["name"] if parsed_file.get("classes") else "Unknown"
        graph_store.upsert_field(
            first_class, pkg,
            field["name"], field.get("type", "Object"),
        )
        node_count += 1

    return node_count, rel_count
