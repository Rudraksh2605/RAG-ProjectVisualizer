"""
Tree-sitter-based AST parser for Java and Kotlin.

Extracts structured relationships (inheritance, method calls, field
types, annotations) that the regex parser in `parser.py` cannot
reliably detect.  These relationships are stored in Neo4j to enable
GraphRAG — answering structural / dependency questions via Cypher
rather than approximate vector search.

Falls back gracefully if tree-sitter is not installed.
"""

import logging
import os
from typing import List, Dict, Optional, Tuple

log = logging.getLogger("tree_sitter_parser")

# ── Lazy-load tree-sitter to avoid hard crash on import ────────

_TS_AVAILABLE = False
_java_language = None
_kotlin_language = None

try:
    import tree_sitter_java as ts_java
    import tree_sitter_kotlin as ts_kotlin
    from tree_sitter import Language, Parser

    _java_language = Language(ts_java.language())
    _kotlin_language = Language(ts_kotlin.language())
    _TS_AVAILABLE = True
    log.info("Tree-sitter loaded successfully (Java + Kotlin).")
except Exception as e:
    log.warning("Tree-sitter not available (%s). Graph extraction will "
                "fall back to regex parser.", e)


def is_available() -> bool:
    """Return True if tree-sitter grammars are ready."""
    return _TS_AVAILABLE


# ── Public API ─────────────────────────────────────────────────

def extract_graph_data(file_path: str, source: str = None) -> Optional[Dict]:
    """
    Parse a Java or Kotlin file and return a dict of graph-ready data:

        {
            "file_path": str,
            "language": "java" | "kotlin",
            "package": str,
            "imports": [str],
            "classes": [
                {
                    "name": str,
                    "superclass": str | None,
                    "interfaces": [str],
                    "annotations": [str],
                    "methods": [
                        {
                            "name": str,
                            "return_type": str,
                            "params": [{"name": str, "type": str}],
                            "calls": [str],      # method names called
                            "local_types": [str], # types referenced
                        }
                    ],
                    "fields": [{"name": str, "type": str}],
                }
            ],
        }
    """
    if not _TS_AVAILABLE:
        return None

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".java":
        language = _java_language
        lang_name = "java"
    elif ext == ".kt":
        language = _kotlin_language
        lang_name = "kotlin"
    else:
        return None

    if source is None:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception:
            return None

    parser = Parser(language)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    result = {
        "file_path": file_path,
        "language": lang_name,
        "package": _extract_package(root, source, lang_name),
        "imports": _extract_imports(root, source, lang_name),
        "classes": [],
    }

    class_nodes = _find_class_nodes(root, lang_name)
    for cls_node in class_nodes:
        cls_data = _extract_class_data(cls_node, source, lang_name)
        if cls_data:
            result["classes"].append(cls_data)

    return result


# ── Internal helpers ───────────────────────────────────────────

def _text(node, source: str) -> str:
    """Get the text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte]


def _extract_package(root, source: str, lang: str) -> str:
    """Extract package declaration."""
    for child in root.children:
        if child.type == "package_declaration":
            # Java: package com.example.app;
            for sub in child.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return _text(sub, source)
        elif child.type == "package_header":
            # Kotlin: package com.example.app
            for sub in child.children:
                if sub.type in ("identifier", "scoped_identifier"):
                    return _text(sub, source)
    return ""


def _extract_imports(root, source: str, lang: str) -> List[str]:
    """Extract import statements."""
    imports = []
    for child in root.children:
        if child.type in ("import_declaration", "import_header"):
            for sub in child.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    imports.append(_text(sub, source))
                    break
        elif child.type == "import_list":
            # Kotlin groups imports in an import_list node
            for imp in child.children:
                if imp.type == "import_header":
                    for sub in imp.children:
                        if sub.type in ("scoped_identifier", "identifier"):
                            imports.append(_text(sub, source))
                            break
    return imports


def _find_class_nodes(root, lang: str) -> List:
    """Find all class/interface/object/enum declaration nodes."""
    target_types = {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "object_declaration",
    }
    nodes = []
    _walk(root, target_types, nodes)
    return nodes


def _walk(node, target_types: set, results: list):
    """Recursively walk the AST to find nodes of target types."""
    if node.type in target_types:
        results.append(node)
    for child in node.children:
        _walk(child, target_types, results)


def _extract_class_data(cls_node, source: str, lang: str) -> Optional[Dict]:
    """Extract class name, superclass, interfaces, methods, fields."""
    name = None
    superclass = None
    interfaces = []
    annotations = []
    methods = []
    fields = []

    for child in cls_node.children:
        if child.type == "identifier":
            name = _text(child, source)

        elif child.type in ("superclass", "delegation_specifier"):
            superclass = _text(child, source).strip(": ").strip()

        elif child.type == "super_interfaces":
            for sub in child.children:
                if sub.type in ("type_identifier", "type_list"):
                    interfaces.append(_text(sub, source))

        elif child.type in ("modifiers", "annotation"):
            ann_text = _text(child, source)
            for line in ann_text.split("\n"):
                line = line.strip()
                if line.startswith("@"):
                    ann_name = line.split("(")[0].lstrip("@").strip()
                    if ann_name:
                        annotations.append(ann_name)

        elif child.type == "class_body":
            methods, fields = _extract_members(child, source, lang)

        elif child.type == "enum_body":
            methods, fields = _extract_members(child, source, lang)

    # Also extract annotations from the parent if they are siblings
    if cls_node.parent:
        for sibling in cls_node.parent.children:
            if sibling.type in ("modifiers",) and sibling.end_byte <= cls_node.start_byte:
                ann_text = _text(sibling, source)
                for line in ann_text.split("\n"):
                    line = line.strip()
                    if line.startswith("@"):
                        ann_name = line.split("(")[0].lstrip("@").strip()
                        if ann_name and ann_name not in annotations:
                            annotations.append(ann_name)

    # Try to extract superclass and interfaces from superclass_list
    # or delegation_specifiers (Kotlin-specific)
    if superclass is None:
        for child in cls_node.children:
            if child.type in ("superclass_type", "delegation_specifiers"):
                parts = _text(child, source).split(",")
                if parts:
                    superclass = parts[0].strip().strip(": ").strip()
                    interfaces.extend([p.strip() for p in parts[1:] if p.strip()])

    if not name:
        return None

    return {
        "name": name,
        "superclass": superclass,
        "interfaces": interfaces,
        "annotations": annotations,
        "methods": methods,
        "fields": fields,
    }


def _extract_members(body_node, source: str, lang: str) -> Tuple[List[Dict], List[Dict]]:
    """Extract methods and fields from a class body node."""
    methods = []
    fields = []

    for child in body_node.children:
        # Methods
        if child.type in ("method_declaration", "function_declaration",
                          "constructor_declaration"):
            method_data = _extract_method(child, source, lang)
            if method_data:
                methods.append(method_data)

        # Fields
        elif child.type in ("field_declaration", "property_declaration"):
            field_data = _extract_field(child, source, lang)
            if field_data:
                fields.append(field_data)

        # Class body declarations (Java inner constructs)
        elif child.type == "class_body_declaration":
            for sub in child.children:
                if sub.type in ("method_declaration", "constructor_declaration"):
                    md = _extract_method(sub, source, lang)
                    if md:
                        methods.append(md)
                elif sub.type == "field_declaration":
                    fd = _extract_field(sub, source, lang)
                    if fd:
                        fields.append(fd)

    return methods, fields


def _extract_method(node, source: str, lang: str) -> Optional[Dict]:
    """Extract method name, return type, params, and method calls."""
    name = None
    return_type = "void"
    params = []
    calls = []
    local_types = []

    for child in node.children:
        if child.type == "identifier":
            if name is None:
                name = _text(child, source)

        elif child.type in ("type_identifier", "void_type",
                            "integral_type", "floating_point_type",
                            "boolean_type", "generic_type"):
            return_type = _text(child, source)

        elif child.type in ("formal_parameters", "function_value_parameters",
                            "parameter_list"):
            params = _extract_params(child, source, lang)

        elif child.type in ("block", "function_body"):
            calls, local_types = _extract_calls_and_types(child, source)

    if not name or name in ("if", "for", "while", "switch", "catch"):
        return None

    return {
        "name": name,
        "return_type": return_type,
        "params": params,
        "calls": list(set(calls)),
        "local_types": list(set(local_types)),
    }


def _extract_params(params_node, source: str, lang: str) -> List[Dict]:
    """Extract parameter names and types."""
    params = []
    for child in params_node.children:
        if child.type in ("formal_parameter", "parameter",
                          "function_value_parameter"):
            p_name = ""
            p_type = ""
            for sub in child.children:
                if sub.type == "identifier":
                    p_name = _text(sub, source)
                elif sub.type in ("type_identifier", "generic_type",
                                  "integral_type", "array_type",
                                  "user_type"):
                    p_type = _text(sub, source)
            if p_name:
                params.append({"name": p_name, "type": p_type or "Object"})
    return params


def _extract_field(node, source: str, lang: str) -> Optional[Dict]:
    """Extract a field's name and type."""
    f_name = ""
    f_type = ""
    for child in node.children:
        if child.type == "variable_declarator":
            for sub in child.children:
                if sub.type == "identifier":
                    f_name = _text(sub, source)
        elif child.type == "identifier":
            if not f_name:
                f_name = _text(child, source)
        elif child.type in ("type_identifier", "generic_type",
                            "integral_type", "array_type",
                            "user_type"):
            f_type = _text(child, source)

    if f_name:
        return {"name": f_name, "type": f_type or "Object"}
    return None


def _extract_calls_and_types(body_node, source: str) -> Tuple[List[str], List[str]]:
    """Walk a method body to find method invocations and type references."""
    calls = []
    types = []

    def _walk_body(node):
        if node.type in ("method_invocation", "call_expression"):
            # Try to find the method name being called
            for child in node.children:
                if child.type == "identifier":
                    calls.append(_text(child, source))
                elif child.type in ("field_access", "member_access_expression"):
                    # e.g., repository.findAll() -> "findAll"
                    for sub in child.children:
                        if sub.type == "identifier":
                            calls.append(_text(sub, source))

        elif node.type in ("type_identifier", "user_type"):
            types.append(_text(node, source))

        elif node.type == "object_creation_expression":
            for child in node.children:
                if child.type == "type_identifier":
                    types.append(_text(child, source))

        for child in node.children:
            _walk_body(child)

    _walk_body(body_node)
    return calls, types
