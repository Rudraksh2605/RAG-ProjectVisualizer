"""
Semantic code chunker — converts parsed file data into text chunks
with rich metadata for RAG retrieval.

Chunk granularity:
  • CLASS   – class signature + fields + method signatures
  • METHOD  – full method source (for important methods)
  • CONFIG  – manifest / gradle contents
  • LAYOUT  – XML layout widget summary
"""

from typing import List, Dict, Optional
from utils.helpers import truncate
import config


class CodeChunk:
    """A single indexable chunk with metadata."""

    __slots__ = (
        "id", "content", "component_name", "component_type",
        "layer", "package", "file_path", "chunk_type", "language",
    )

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        return {s: getattr(self, s, "") for s in self.__slots__}

    def metadata(self) -> dict:
        """Return metadata dict for ChromaDB."""
        return {
            "component_name": self.component_name or "",
            "component_type": self.component_type or "",
            "layer": self.layer or "",
            "package": self.package or "",
            "file_path": self.file_path or "",
            "chunk_type": self.chunk_type or "",
            "language": self.language or "",
        }


def chunk_parsed_files(parsed_files: List[Dict]) -> List[CodeChunk]:
    """
    Convert a list of parsed file dicts (from parser.py) into CodeChunks.
    """
    chunks: List[CodeChunk] = []
    idx = 0

    for pf in parsed_files:
        if pf is None:
            continue

        path = pf.get("path", "")
        ftype = pf.get("type", pf.get("language", ""))

        # ── Java / Kotlin files ──────────────────────────────
        if ftype in ("java", "kotlin"):
            pkg = pf.get("package", "")

            for cls in pf.get("classes", []):
                # Class-level chunk: signature + fields + method names
                class_text = _build_class_chunk_text(cls, pf)
                chunks.append(CodeChunk(
                    id=f"chunk_{idx}",
                    content=truncate(class_text, config.CHUNK_MAX_CHARS),
                    component_name=cls["name"],
                    component_type=cls.get("component_type", "Class"),
                    layer=cls.get("layer", "Other"),
                    package=pkg,
                    file_path=path,
                    chunk_type="CLASS",
                    language=ftype,
                ))
                idx += 1

            # Method-level chunks (only for non-trivial methods)
            source = pf.get("source", "")
            for method in pf.get("methods", []):
                method_src = _extract_method_source(source, method["name"])
                if method_src and len(method_src) > 60:
                    cls_name = pf["classes"][0]["name"] if pf.get("classes") else "Unknown"
                    chunks.append(CodeChunk(
                        id=f"chunk_{idx}",
                        content=truncate(method_src, config.CHUNK_MAX_CHARS),
                        component_name=f"{cls_name}.{method['name']}",
                        component_type="Method",
                        layer=pf["classes"][0].get("layer", "Other") if pf.get("classes") else "Other",
                        package=pkg,
                        file_path=path,
                        chunk_type="METHOD",
                        language=ftype,
                    ))
                    idx += 1

        # ── Manifest ─────────────────────────────────────────
        elif ftype == "manifest":
            manifest_text = _build_manifest_chunk_text(pf)
            chunks.append(CodeChunk(
                id=f"chunk_{idx}",
                content=truncate(manifest_text, config.CHUNK_MAX_CHARS),
                component_name="AndroidManifest",
                component_type="Config",
                layer="Config",
                package=pf.get("package", ""),
                file_path=path,
                chunk_type="CONFIG",
                language="xml",
            ))
            idx += 1

        # ── Layout XML ───────────────────────────────────────
        elif ftype == "layout":
            layout_text = _build_layout_chunk_text(pf)
            if layout_text:
                chunks.append(CodeChunk(
                    id=f"chunk_{idx}",
                    content=truncate(layout_text, config.CHUNK_MAX_CHARS),
                    component_name=_layout_name(path),
                    component_type="Layout",
                    layer="UI",
                    package="",
                    file_path=path,
                    chunk_type="LAYOUT",
                    language="xml",
                ))
                idx += 1

        # ── Gradle ───────────────────────────────────────────
        elif ftype == "gradle":
            gradle_text = _build_gradle_chunk_text(pf)
            chunks.append(CodeChunk(
                id=f"chunk_{idx}",
                content=truncate(gradle_text, config.CHUNK_MAX_CHARS),
                component_name="build.gradle",
                component_type="Config",
                layer="Config",
                package="",
                file_path=path,
                chunk_type="CONFIG",
                language="gradle",
            ))
            idx += 1

    return chunks


# ── Text builders ────────────────────────────────────────────────

def _build_class_chunk_text(cls: dict, parsed_file: dict) -> str:
    """Build a rich text representation of a class for embedding."""
    lines = []
    pkg = parsed_file.get("package", "")
    if pkg:
        lines.append(f"Package: {pkg}")

    name = cls["name"]
    superclass = cls.get("superclass", "")
    interfaces = cls.get("interfaces", [])
    annotations = cls.get("annotations", [])
    ctype = cls.get("component_type", "Class")
    layer = cls.get("layer", "")

    sig_parts = [f"[{ctype}]", f"class {name}"]
    if superclass:
        sig_parts.append(f"extends {superclass}")
    if interfaces:
        sig_parts.append(f"implements {', '.join(interfaces)}")
    lines.append(" ".join(sig_parts))

    if annotations:
        lines.append(f"Annotations: {', '.join('@' + a for a in annotations)}")
    if layer:
        lines.append(f"Layer: {layer}")

    # Fields
    fields = parsed_file.get("fields", [])
    if fields:
        lines.append("Fields:")
        for f in fields[:20]:
            lines.append(f"  {f['type']} {f['name']}")

    # Method signatures
    methods = parsed_file.get("methods", [])
    if methods:
        lines.append("Methods:")
        for m in methods[:30]:
            ret = m.get("return_type", "void")
            lines.append(f"  {ret} {m['name']}({m.get('params', '')})")

    return "\n".join(lines)


def _build_manifest_chunk_text(pf: dict) -> str:
    lines = [f"Android Manifest — Package: {pf.get('package', 'N/A')}"]
    if pf.get("min_sdk"):
        lines.append(f"Min SDK: {pf['min_sdk']}")
    if pf.get("target_sdk"):
        lines.append(f"Target SDK: {pf['target_sdk']}")
    if pf.get("activities"):
        lines.append("Activities: " + ", ".join(pf["activities"]))
    if pf.get("services"):
        lines.append("Services: " + ", ".join(pf["services"]))
    if pf.get("receivers"):
        lines.append("Receivers: " + ", ".join(pf["receivers"]))
    if pf.get("permissions"):
        lines.append("Permissions: " + ", ".join(pf["permissions"]))
    return "\n".join(lines)


def _build_layout_chunk_text(pf: dict) -> str:
    widgets = pf.get("widgets", [])
    if not widgets:
        return ""
    name = _layout_name(pf["path"])
    return f"Layout: {name}\nWidgets: {', '.join(widgets)}"


def _build_gradle_chunk_text(pf: dict) -> str:
    lines = ["Gradle build configuration"]
    if pf.get("plugins"):
        lines.append("Plugins: " + ", ".join(pf["plugins"]))
    if pf.get("dependencies"):
        lines.append("Dependencies:")
        for dep in pf["dependencies"]:
            lines.append(f"  - {dep}")
    if pf.get("min_sdk"):
        lines.append(f"Min SDK: {pf['min_sdk']}")
    if pf.get("compile_sdk"):
        lines.append(f"Compile SDK: {pf['compile_sdk']}")
    return "\n".join(lines)


def _extract_method_source(full_source: str, method_name: str) -> str:
    """
    Best-effort extraction of a method body from full source.
    Finds the method signature and returns up to the matching closing brace.
    """
    import re
    # Find start of method
    pattern = re.compile(
        rf"(?:(?:public|private|protected|override|open|suspend|internal|static|final)\s+)*"
        rf"(?:fun\s+)?(?:[\w<>\[\]?,\s]+\s+)?{re.escape(method_name)}\s*\(",
        re.MULTILINE,
    )
    match = pattern.search(full_source)
    if not match:
        return ""

    start = match.start()
    # Find the opening brace after the match
    brace_pos = full_source.find("{", match.end())
    if brace_pos == -1:
        return ""

    # Count braces to find matching close
    depth = 1
    pos = brace_pos + 1
    while pos < len(full_source) and depth > 0:
        if full_source[pos] == "{":
            depth += 1
        elif full_source[pos] == "}":
            depth -= 1
        pos += 1

    return full_source[start:pos].strip()


def _layout_name(path: str) -> str:
    """Extract layout file name from its path."""
    import os
    return os.path.splitext(os.path.basename(path))[0]
