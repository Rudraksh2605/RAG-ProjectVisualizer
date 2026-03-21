"""
PlantUML diagram generators — class, sequence, activity, state-machine,
component, use-case, package, deployment, and navigation diagrams.

All generators use RAG to retrieve relevant code chunks before asking
the LLM to produce PlantUML syntax.

Includes robust extraction, validation, auto-repair, and LLM retry
to ensure rendered diagrams even when the LLM produces imperfect syntax.

Improvements over original:
  - Data-driven DIAGRAM_SPECS replaces 9 copy-paste functions
  - In-memory diagram cache keyed on (type, focus, project_fingerprint)
  - Parallel generation via ThreadPoolExecutor
  - Type-specific validation (checks for diagram keywords)
  - Expanded repair patterns (duplicate tags, HTML, activate/deactivate, alt/end)
  - Smart skinparam merging (no duplicates)
  - Structured logging instead of bare print()
"""

import re
import logging
from typing import Dict, Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from core import rag_engine
from core.ollama_client import generate
import config

log = logging.getLogger("plantuml")


# ═══════════════════════════════════════════════════════════════
#  Diagram specifications — single source of truth
# ═══════════════════════════════════════════════════════════════

# Each entry defines:
#   display_name  – UI label
#   query_default – retrieval question when no focus is given
#   query_focused – retrieval question with {focus} placeholder (or None)
#   top_k         – how many chunks to retrieve
#   layer_filter  – optional metadata filter for retrieval
DIAGRAM_SPECS: Dict[str, dict] = {
    "class_diagram": {
        "display_name": "Class Diagram",
        "query_default": (
            "Show the 4-6 most important classes in this project with their "
            "key fields, public methods, relationships, and architectural layers."
        ),
        "query_focused": (
            "Show the class '{focus}' and its 3-5 closest collaborators with "
            "their fields, methods, and relationships."
        ),
        "has_focus": True,
        "top_k": 15,
    },
    "sequence_diagram": {
        "display_name": "Sequence Diagram",
        "query_default": (
            "Show the most important user interaction flow (e.g. login or main feature) "
            "with the participants, messages, and error handling."
        ),
        "query_focused": (
            "Show the flow when '{focus}' is triggered, including the participants, "
            "messages, and one request-response round-trip."
        ),
        "has_focus": True,
        "top_k": 15,
    },
    "activity_diagram": {
        "display_name": "Activity Diagram",
        "query_default": (
            "Show the main user journey from app launch to the primary feature, "
            "including key decisions and steps."
        ),
        "has_focus": False,
        "top_k": 15,
        "layer_filter": "UI",
    },
    "state_diagram": {
        "display_name": "State Machine Diagram",
        "query_default": (
            "Show the lifecycle states and transitions for the main Activity or Fragment, "
            "including callbacks and guards. "
            "IMPORTANT: If you use spaces in state names, you MUST declare them first "
            "(e.g., `state \"My State\" as my_state`)."
        ),
        "query_focused": (
            "Show the lifecycle states and transitions for '{focus}', "
            "including entry/exit actions and event guards. "
            "IMPORTANT: If you use spaces in state names, you MUST declare them first "
            "(e.g., `state \"My State\" as my_state`)."
        ),
        "has_focus": True,
        "top_k": 15,
    },
    "component_diagram": {
        "display_name": "Component Diagram",
        "query_default": (
            "Show the app's major components grouped by feature area, "
            "their stereotypes, and how they connect."
        ),
        "has_focus": False,
        "top_k": 15,
    },
    "usecase_diagram": {
        "display_name": "Use Case Diagram",
        "query_default": (
            "Describe the distinct business features and user capabilities in this app. "
            "Focus on actions the user can take (e.g., 'Take a Quiz', 'View Profile', 'Register Account', 'Chat with Bot') "
            "rather than just listing UI screens. Summarize the core functionalities and their relationships."
        ),
        "has_focus": False,
        "top_k": 30,
    },
    "package_diagram": {
        "display_name": "Package Diagram",
        "query_default": (
            "Show the 3-4 architectural layers, 2-3 key classes in each, "
            "and inter-layer dependencies."
        ),
        "has_focus": False,
        "top_k": 15,
    },
    "deployment_diagram": {
        "display_name": "Deployment Diagram",
        "query_default": (
            "Show the Android device, external cloud services, API servers, "
            "and their connection protocols."
        ),
        "has_focus": False,
        "top_k": 15,
    },
    "navigation_diagram": {
        "display_name": "Navigation Diagram",
        "query_default": (
            "List EVERY Activity and Fragment in this project. For each one, list ALL "
            "Intent launches, startActivity calls, fragment transactions, navigation actions, "
            "and button click handlers that navigate to other screens. Include the launcher "
            "Activity and all back navigation. Show ALL screens, not just a subset. "
            "IMPORTANT: If you use spaces in state names, you MUST declare them first "
            "(e.g., `state \"My State\" as my_state`)."
        ),
        "has_focus": False,
        "top_k": 40,
        "layer_filter": "UI",
    },
}


# ═══════════════════════════════════════════════════════════════
#  Registry — maps display names to (generator_key, needs_focus)
# ═══════════════════════════════════════════════════════════════

# Built after the wrapper functions are defined (see below).
# Placeholder — populated at module bottom.
DIAGRAM_REGISTRY = {}


# ═══════════════════════════════════════════════════════════════
#  Diagram cache — keyed on (type, focus, project_fingerprint)
# ═══════════════════════════════════════════════════════════════

_diagram_cache: Dict[tuple, str] = {}


def _cache_key(diagram_type: str, focus: Optional[str]) -> tuple:
    fp = getattr(rag_engine, "_project_fingerprint", None)
    return (diagram_type, focus or "", fp or "")


def clear_diagram_cache():
    """Clear all cached diagrams (call after re-indexing)."""
    _diagram_cache.clear()
    log.info("Diagram cache cleared")


# ═══════════════════════════════════════════════════════════════
#  Unified generator — replaces 9 copy-paste functions
# ═══════════════════════════════════════════════════════════════

def generate_diagram(diagram_type: str, focus: Optional[str] = None) -> str:
    """
    Generate a PlantUML diagram of the given type.

    Args:
        diagram_type: Key from DIAGRAM_SPECS (e.g. "class_diagram")
        focus:        Optional focus class/flow for types that support it

    Returns:
        Valid PlantUML code string.
    """
    # Check cache first
    key = _cache_key(diagram_type, focus)
    if key in _diagram_cache:
        log.info("Cache hit for %s (focus=%s)", diagram_type, focus)
        return _diagram_cache[key]

    spec = DIAGRAM_SPECS.get(diagram_type)
    if not spec:
        log.error("Unknown diagram type: %s", diagram_type)
        return "@startuml\n' Unknown diagram type\n@enduml"

    # Build retrieval question
    if focus and spec.get("has_focus") and spec.get("query_focused"):
        question = spec["query_focused"].format(focus=focus)
    else:
        question = spec["query_default"]

    raw = rag_engine.query(
        question,
        analysis_type=diagram_type,
        top_k=spec.get("top_k", config.RAG_TOP_K),
        layer_filter=spec.get("layer_filter"),
    )

    result = _extract_and_validate(raw, diagram_type)

    # Cache the result
    _diagram_cache[key] = result
    log.info("Generated and cached %s (focus=%s)", diagram_type, focus)
    return result


# ── Backward-compatible convenience wrappers ──────────────────
# (so existing app.py code keeps working without changes)

def generate_class_diagram(focus_class: str = None) -> str:
    return generate_diagram("class_diagram", focus_class)

def generate_sequence_diagram(focus: str = None) -> str:
    return generate_diagram("sequence_diagram", focus)

def generate_activity_diagram() -> str:
    return generate_diagram("activity_diagram")

def generate_state_diagram(focus_class: str = None) -> str:
    return generate_diagram("state_diagram", focus_class)

def generate_component_diagram() -> str:
    return generate_diagram("component_diagram")

def generate_usecase_diagram() -> str:
    return generate_diagram("usecase_diagram")

def generate_package_diagram() -> str:
    return generate_diagram("package_diagram")

def generate_deployment_diagram() -> str:
    return generate_diagram("deployment_diagram")

def generate_navigation_diagram() -> str:
    return generate_diagram("navigation_diagram")


# ── Now populate DIAGRAM_REGISTRY with actual callable functions ──
# app.py expects: display_name -> (callable, needs_focus)
_WRAPPER_MAP = {
    "class_diagram":      generate_class_diagram,
    "sequence_diagram":   generate_sequence_diagram,
    "activity_diagram":   generate_activity_diagram,
    "state_diagram":      generate_state_diagram,
    "component_diagram":  generate_component_diagram,
    "usecase_diagram":    generate_usecase_diagram,
    "package_diagram":    generate_package_diagram,
    "deployment_diagram": generate_deployment_diagram,
    "navigation_diagram": generate_navigation_diagram,
}

DIAGRAM_REGISTRY.update({
    spec["display_name"]: (_WRAPPER_MAP[key], spec.get("has_focus", False))
    for key, spec in DIAGRAM_SPECS.items()
})


# ═══════════════════════════════════════════════════════════════
#  Parallel generation — generate multiple diagrams concurrently
# ═══════════════════════════════════════════════════════════════

def generate_diagrams_parallel(
    diagram_types: List[str],
    focus_map: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Generate multiple diagrams in parallel using ThreadPoolExecutor.

    Args:
        diagram_types: List of diagram type keys from DIAGRAM_SPECS
        focus_map:     Optional {diagram_type: focus_value}

    Returns:
        Dict mapping diagram_type -> PlantUML code
    """
    focus_map = focus_map or {}
    results = {}
    max_workers = getattr(config, "PARALLEL_MAX_WORKERS", 3)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(generate_diagram, dt, focus_map.get(dt)):  dt
            for dt in diagram_types
        }
        for future in as_completed(futures):
            dt = futures[future]
            try:
                results[dt] = future.result()
            except Exception as e:
                log.error("Parallel generation failed for %s: %s", dt, e)
                results[dt] = f"@startuml\n' Error generating {dt}: {e}\n@enduml"

    return results


# ═══════════════════════════════════════════════════════════════
#  Skinparam injection — smart merging, no duplicates
# ═══════════════════════════════════════════════════════════════

_DEFAULT_SKINPARAMS = {
    'defaultFontName': '"Segoe UI"',
    'defaultFontSize': '13',
    'shadowing': 'false',
    'roundCorner': '10',
    'BackgroundColor': '#FEFEFE',
    'ArrowColor': '#1565C0',
    'ArrowFontColor': '#333333',
    'ArrowFontSize': '12',
    'ArrowThickness': '1.5',
    'noteBorderColor': '#FFB300',
    'noteBackgroundColor': '#FFF9C4',
    'noteFontColor': '#333333',
    'titleFontSize': '18',
    'titleFontColor': '#1a1a2e',
    'titleFontStyle': 'bold',
    'ClassBackgroundColor': '#E3F2FD',
    'ClassBorderColor': '#1976D2',
    'ClassFontColor': '#1a1a2e',
    'ClassAttributeFontColor': '#37474F',
    'ClassStereotypeFontColor': '#7B1FA2',
    'PackageBackgroundColor': '#F3E5F5',
    'PackageBorderColor': '#7B1FA2',
    'PackageFontColor': '#4A148C',
    'ComponentBackgroundColor': '#E8F5E9',
    'ComponentBorderColor': '#388E3C',
    'ComponentFontColor': '#1B5E20',
    'UsecaseBackgroundColor': '#E3F2FD',
    'UsecaseBorderColor': '#1565C0',
    'UsecaseFontColor': '#0D47A1',
    'ActorBorderColor': '#1565C0',
    'ActorFontColor': '#1a1a2e',
    'StateBackgroundColor': '#E8EAF6',
    'StateBorderColor': '#283593',
    'StateFontColor': '#1A237E',
    'ParticipantBackgroundColor': '#E3F2FD',
    'ParticipantBorderColor': '#1565C0',
    'ParticipantFontColor': '#0D47A1',
    'DatabaseBackgroundColor': '#FFF3E0',
    'DatabaseBorderColor': '#E65100',
    'DatabaseFontColor': '#BF360C',
    'CloudBackgroundColor': '#E0F7FA',
    'CloudBorderColor': '#00838F',
    'CloudFontColor': '#006064',
    'NodeBackgroundColor': '#F3E5F5',
    'NodeBorderColor': '#6A1B9A',
    'NodeFontColor': '#4A148C',
    'SequenceLifeLineBorderColor': '#1565C0',
    'SequenceGroupBackgroundColor': '#E8EAF6',
}

# Regex to parse skinparam lines: "skinparam key value" or "skinparam key { ... }"
_RE_SKINPARAM_LINE = re.compile(
    r'^\s*skinparam\s+(\S+)\s+(.+)$', re.IGNORECASE | re.MULTILINE
)


def _inject_skinparam(code: str) -> str:
    """
    Smart skinparam injection — merges defaults with LLM-provided params.
    LLM values take priority. No duplicate keys emitted.
    """
    # Parse existing skinparams from the code
    existing = {}
    for m in _RE_SKINPARAM_LINE.finditer(code):
        existing[m.group(1)] = m.group(2).strip()

    # Build merged set: defaults first, then LLM overrides
    merged = dict(_DEFAULT_SKINPARAMS)
    merged.update(existing)

    # Build the skinparam block
    skinparam_lines = [f"skinparam {k} {v}" for k, v in merged.items()]
    skinparam_block = "\n".join(skinparam_lines)

    # Remove all existing skinparam lines from the body (we'll re-inject merged)
    cleaned = _RE_SKINPARAM_LINE.sub("", code)

    # Also handle skinparam blocks like: skinparam class { ... }
    # Keep those as-is since they are component-specific
    return cleaned.replace(
        "@startuml",
        f"@startuml\n{skinparam_block}",
        1,
    )


# ═══════════════════════════════════════════════════════════════
#  PlantUML extraction, validation, repair, and retry
# ═══════════════════════════════════════════════════════════════

# Regex to capture @startuml ... @enduml blocks
_PUML_BLOCK_RE = re.compile(
    r'@startuml.*?@enduml', re.DOTALL | re.IGNORECASE
)

# Code fence extraction pattern
_CODE_FENCE_RE = re.compile(
    r'```(?:plantuml|puml|uml)?\s*\n(.*?)```',
    re.DOTALL | re.IGNORECASE,
)

# Markers that indicate the LLM returned an error
_ERROR_MARKERS = [
    "[Ollama error",
    "[Streaming error",
    "I cannot generate",
    "I'm sorry",
    "I apologize",
    "As an AI",
]

# ── Type-specific keywords for validation ──────────────────────
_TYPE_MARKERS = {
    "class_diagram": ["class "],
    "sequence_diagram": ["participant ", "actor ", "->"],
    "activity_diagram": ["start", ":"],
    "state_diagram": ["state ", "[*]"],
    "component_diagram": ["component ", "["],
    "usecase_diagram": ["usecase ", "actor "],
    "package_diagram": ["package "],
    "deployment_diagram": ["node ", "database ", "cloud ", "artifact "],
    "navigation_diagram": ["state ", "[*]"],
}

# ── Precompiled patterns for _repair_plantuml ──────────────────
_RE_COLON_EXTENDS = re.compile(
    r'^(\s*(?:abstract\s+)?class\s+\w+)\s*:\s*(\w+)',
    re.MULTILINE,
)
_RE_EXTENDS_IFACE = re.compile(
    r'^(\s*(?:abstract\s+)?class\s+\w+)\s*extends\s+(I[A-Z]\w*Interface|\w*able)',
    re.MULTILINE,
)
_RE_ARROW_TARGET = re.compile(
    r'(-+-\>|\.\.\+\>|<-+-|<\.\.\+)\s+(?!["(])([A-Z][a-zA-Z]*(?:\s+[A-Za-z/]+)+)\s*$',
    re.MULTILINE,
)
_RE_ARROW_SOURCE = re.compile(
    r'^\s*(?!["(])([A-Z][a-zA-Z]*(?:\s+[A-Za-z/]+)+)\s+(-+-\>|\.\.\+\>)',
    re.MULTILINE,
)
_COMMENTARY_PREFIXES = (
    "here is", "here's", "below is", "this diagram",
    "note:", "explanation:", "the above", "as you can see",
    "i hope", "let me", "please note", "sure,",
)

# Pattern to find note directives trapped inside state/class blocks
_RE_NOTE_INSIDE_BLOCK = re.compile(
    r'(state\s+"[^"]*"\s+as\s+\w+)\s*\{\s*(note\s+\w+\s+of\s+\w+\s*:.*)\s*\}',
    re.IGNORECASE,
)

# Pattern for duplicate @startuml/@enduml tags
_RE_DUPLICATE_STARTUML = re.compile(r'(@startuml\s*\n?){2,}', re.IGNORECASE)
_RE_DUPLICATE_ENDUML = re.compile(r'(@enduml\s*\n?){2,}', re.IGNORECASE)

# Pattern for stray HTML tags
_RE_HTML_TAGS = re.compile(r'</?(?:b|i|u|em|strong|br|p|div|span)(?:\s[^>]*)?\s*/?>', re.IGNORECASE)


def _extract_plantuml(text: str) -> str:
    """
    Robustly extract the PlantUML block from LLM output.

    Strategy (in order):
      1. Regex search for @startuml...@enduml blocks
      2. Extract from ```plantuml or ``` code fences
      3. Fallback: wrap entire output
    """
    if not text or not text.strip():
        return "@startuml\n' Empty diagram\n@enduml"

    # Check if the LLM returned an error message
    text_lower = text.lower()
    for marker in _ERROR_MARKERS:
        if marker.lower() in text_lower:
            log.warning("LLM returned error-like text: %s...", text[:100])
            return "@startuml\n' LLM could not generate diagram\n@enduml"

    # 1. Regex: find all @startuml...@enduml blocks
    matches = _PUML_BLOCK_RE.findall(text)
    if matches:
        best = max(matches, key=len)
        return best.strip()

    # 2. Code fences
    fence_matches = _CODE_FENCE_RE.findall(text)
    if fence_matches:
        body = max(fence_matches, key=len).strip()
        inner = _PUML_BLOCK_RE.findall(body)
        if inner:
            return max(inner, key=len).strip()
        return f"@startuml\n{body}\n@enduml"

    # 3. Fallback: wrap entire output (strip common chat prefixes)
    stripped = text.strip()
    for prefix in [
        "Here is", "Here's", "Below is", "The following",
        "Sure,", "Sure!", "Certainly",
    ]:
        if stripped.lower().startswith(prefix.lower()):
            nl_idx = stripped.find("\n")
            if nl_idx != -1:
                stripped = stripped[nl_idx + 1:].strip()
            break

    return f"@startuml\n{stripped}\n@enduml"


def _validate_plantuml(code: str, diagram_type: str = "general") -> Tuple[bool, str]:
    """
    Syntax validation for PlantUML code.
    Includes both general checks and diagram-type-specific keyword checks.

    Returns (is_valid: bool, error_message: str).
    """
    if not code or len(code.strip()) < 20:
        return False, "PlantUML code is too short or empty"

    if "@startuml" not in code:
        return False, "Missing @startuml tag"

    if "@enduml" not in code:
        return False, "Missing @enduml tag"

    # Check for LLM error messages leaked into diagram
    for marker in _ERROR_MARKERS:
        if marker.lower() in code.lower():
            return False, f"LLM error message in diagram: {marker}"

    # Extract the body between @startuml and @enduml
    start = code.index("@startuml") + len("@startuml")
    end = code.index("@enduml")
    body = code[start:end].strip()

    if not body or body.startswith("'"):
        lines = [l.strip() for l in body.split("\n") if l.strip() and not l.strip().startswith("'")]
        if not lines:
            return False, "Diagram body is empty or contains only comments"

    # Check balanced braces/brackets
    open_braces = body.count("{")
    close_braces = body.count("}")
    if open_braces != close_braces:
        return False, f"Unbalanced braces: {open_braces} open vs {close_braces} close"

    # Type-specific validation: check for expected keywords
    markers = _TYPE_MARKERS.get(diagram_type, [])
    if markers:
        body_lower = body.lower()
        has_any = any(m.lower() in body_lower for m in markers)
        if not has_any:
            return False, (
                f"Diagram type '{diagram_type}' expects at least one of "
                f"{markers} but none were found"
            )

    return True, ""


# ── Patterns to detect duplicate element declarations ──
_RE_ELEMENT_DECL = re.compile(
    r'^\s*(usecase|class|state|participant|actor|component|database|cloud|node|artifact)\s+'
    r'(?:"[^"]*"|\'[^\']*\'|\S+)',
    re.IGNORECASE | re.MULTILINE,
)

# Pattern to match package blocks with their contents
_RE_PACKAGE_BLOCK = re.compile(
    r'package\s+"([^"]+)"\s*\{([^}]*)\}',
    re.IGNORECASE | re.DOTALL,
)

# Pattern to match bare element names (with optional stereotype) inside packages
_RE_BARE_ELEMENT = re.compile(
    r'^\s*(?:<<\w+>>\s+)?(\w+)\s*$',
    re.MULTILINE,
)


def _remove_duplicate_elements(code: str) -> str:
    """
    Remove duplicate element declarations (usecase, class, state, etc.).
    Keeps only the first occurrence of each unique declaration.
    """
    seen = set()
    lines = code.split("\n")
    result = []
    for line in lines:
        m = _RE_ELEMENT_DECL.match(line.strip())
        if m:
            key = m.group(0).strip().lower()
            # Normalize whitespace for comparison
            key = " ".join(key.split())
            if key in seen:
                continue  # skip duplicate
            seen.add(key)
        result.append(line)
    return "\n".join(result)


def _deduplicate_package_members(code: str) -> str:
    """
    Detect element names that appear in multiple package blocks and
    alias duplicates by appending the package name as a suffix.
    Also updates all arrow references to use the new aliased name.

    Example:
        package "Home Screen" { <<Adapter>> ArticleAdapter }
        package "Article Feature" { <<Adapter>> ArticleAdapter }
    becomes:
        package "Home Screen" { <<Adapter>> ArticleAdapter }
        package "Article Feature" { <<Adapter>> ArticleAdapter_ArticleFeature }
    with arrow references updated accordingly.
    """
    # Collect all (element_name, package_name) pairs
    pkg_elements = {}  # element_name -> [package_name, ...]
    for pkg_match in _RE_PACKAGE_BLOCK.finditer(code):
        pkg_name = pkg_match.group(1)
        pkg_body = pkg_match.group(2)
        for elem_match in _RE_BARE_ELEMENT.finditer(pkg_body):
            elem_name = elem_match.group(1)
            if elem_name.lower() in ("end", "start", "stop"):
                continue
            pkg_elements.setdefault(elem_name, []).append(pkg_name)

    # Find elements appearing in more than one package
    duplicates = {name: pkgs for name, pkgs in pkg_elements.items() if len(pkgs) > 1}
    if not duplicates:
        return code

    # For each duplicate, alias all occurrences except the first
    rename_map = {}  # (element_name, package_name) -> new_alias
    for elem_name, pkgs in duplicates.items():
        for pkg_name in pkgs[1:]:  # keep first occurrence as-is
            safe_pkg = re.sub(r'\W+', '', pkg_name)
            alias = f"{elem_name}_{safe_pkg}"
            rename_map[(elem_name, pkg_name)] = alias

    # Apply renames inside package blocks
    def _replace_in_package(match):
        pkg_name = match.group(1)
        pkg_body = match.group(2)
        for (elem, pkg), alias in rename_map.items():
            if pkg == pkg_name:
                # Replace the bare element name inside this package body
                pkg_body = re.sub(
                    rf'(<<\w+>>\s+)?{re.escape(elem)}(\s*)$',
                    rf'\g<1>{alias}\2',
                    pkg_body,
                    flags=re.MULTILINE,
                )
        return f'package "{pkg_name}" {{{pkg_body}}}'

    code = _RE_PACKAGE_BLOCK.sub(_replace_in_package, code)

    # Update arrow references outside packages
    for (elem_name, pkg_name), alias in rename_map.items():
        # Replace references in arrows: "OldName -->" or "--> OldName"
        code = re.sub(
            rf'(?<=\s){re.escape(elem_name)}(?=\s*(?:--|\.\.|\-\->|<))',
            alias, code,
        )
        code = re.sub(
            rf'(?<=-->?\s){re.escape(elem_name)}(?=\s|$)',
            alias, code,
            flags=re.MULTILINE,
        )

    return code


def _strip_llm_skinparams(code: str) -> str:
    """
    Remove all LLM-generated skinparam lines and blocks.
    Our _inject_skinparam will add the correct theme later.
    """
    # Remove simple skinparam lines
    code = _RE_SKINPARAM_LINE.sub("", code)
    # Remove skinparam blocks like: skinparam class { ... }
    code = re.sub(
        r'skinparam\s+\w+\s*\{[^}]*\}',
        '', code, flags=re.IGNORECASE | re.DOTALL,
    )
    return code


def _repair_plantuml(code: str) -> str:
    """
    Attempt common automatic fixes on PlantUML code.
    Uses precompiled regex patterns for performance.
    """
    # Ensure @startuml / @enduml tags
    if "@startuml" not in code:
        code = "@startuml\n" + code
    if "@enduml" not in code:
        code = code + "\n@enduml"

    # ── Fix duplicate @startuml/@enduml tags ──
    code = _RE_DUPLICATE_STARTUML.sub("@startuml\n", code)
    code = _RE_DUPLICATE_ENDUML.sub("@enduml", code)

    # Extract body for repairs
    start = code.index("@startuml")
    end = code.index("@enduml") + len("@enduml")
    header = code[start:start + len("@startuml")]
    footer = code[end - len("@enduml"):end]
    body = code[start + len("@startuml"):end - len("@enduml")]

    # ── Strip LLM-generated skinparams (our theme will be injected later) ──
    body = _strip_llm_skinparams(body)

    # ── Remove duplicate element declarations ──
    body = _remove_duplicate_elements(body)

    # ── Alias duplicate names across different package blocks ──
    body = _deduplicate_package_members(body)

    # ── Fix Kotlin/C++ style inheritance: "class Foo : Bar" → "class Foo extends Bar" ──
    body = _RE_COLON_EXTENDS.sub(r'\1 extends \2', body)

    # ── Fix Kotlin/C++ style interface impl ──
    body = _RE_EXTENDS_IFACE.sub(r'\1 implements \2', body)

    # ── Fix bare multi-word use case names in arrows ──
    body = _RE_ARROW_TARGET.sub(
        lambda m: f'{m.group(1)} ({m.group(2)})',
        body,
    )
    body = _RE_ARROW_SOURCE.sub(
        lambda m: f'({m.group(1)}) {m.group(2)}',
        body,
    )

    # ── Fix notes trapped inside state/class blocks ──
    body = _RE_NOTE_INSIDE_BLOCK.sub(r'\1\n\2', body)

    # ── Fix invalid "-> |Swimlane|" syntax in activity diagrams ──
    # LLMs often generate "-> |User|" but PlantUML expects just "|User|"
    body = re.sub(r'->\s*(\|[^|]+\|)', r'\1', body)

    # ── Fix swimlane ordering: "start" must come AFTER the first swimlane ──
    # PlantUML requires: |Swimlane| \n start   (not: start \n |Swimlane|)
    if re.search(r'\|[^|]+\|', body):
        lines = body.split("\n")
        start_idx = None
        first_swimlane_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower() == "start" and start_idx is None:
                start_idx = i
            if re.match(r'^\s*\|[^|]+\|\s*$', stripped) and first_swimlane_idx is None:
                first_swimlane_idx = i
        # If "start" comes before the first swimlane, move it after
        if (start_idx is not None and first_swimlane_idx is not None
                and start_idx < first_swimlane_idx):
            start_line = lines.pop(start_idx)
            # After popping, the swimlane index shifts down by 1
            lines.insert(first_swimlane_idx, start_line)
            body = "\n".join(lines)

    # ── Remove invalid "-> (SomeName);" standalone goto lines ──
    # LLMs generate these as "go to" statements but PlantUML doesn't support them
    body = re.sub(r'^\s*->\s*\([^)]+\)\s*;?\s*$', '', body, flags=re.MULTILINE)

    # ── Remove stray HTML tags ──
    body = _RE_HTML_TAGS.sub('', body)

    # ── Fix mismatched activate/deactivate in sequence diagrams ──
    activate_count = len(re.findall(r'\bactivate\b', body))
    deactivate_count = len(re.findall(r'\bdeactivate\b', body))
    if activate_count > deactivate_count:
        activate_matches = list(re.finditer(r'\bactivate\s+(\w+)', body))
        for _ in range(activate_count - deactivate_count):
            if activate_matches:
                last = activate_matches.pop()
                body = body.rstrip() + f"\ndeactivate {last.group(1)}"

    # ── Fix unclosed alt/else/opt/loop blocks ──
    alt_opens = len(re.findall(r'\b(alt|opt|loop|group|critical)\b', body))
    alt_ends = len(re.findall(r'\bend\b', body))
    if alt_opens > alt_ends:
        body = body.rstrip() + "\n" + ("end\n" * (alt_opens - alt_ends))

    # Fix unbalanced braces
    open_b = body.count("{")
    close_b = body.count("}")
    if open_b > close_b:
        body = body.rstrip() + "\n" + ("}\n" * (open_b - close_b))

    # Remove stray markdown artifacts
    body = body.replace("```", "")

    # Remove lines that are clearly not PlantUML (common LLM chatter)
    cleaned_lines = []
    for line in body.split("\n"):
        stripped = line.strip().lower()
        if any(stripped.startswith(p) for p in _COMMENTARY_PREFIXES):
            continue
        cleaned_lines.append(line)

    body = "\n".join(cleaned_lines)

    return f"{header}\n{body.strip()}\n{footer}"


def _retry_with_llm(original_code: str, error_msg: str,
                    analysis_type: str) -> str:
    """
    Send the broken PlantUML back to the LLM with the error message,
    asking it to produce valid syntax. Max 1 retry.
    """
    repair_prompt = (
        "The following PlantUML code has a syntax error and cannot be rendered.\n\n"
        f"ERROR: {error_msg}\n\n"
        f"BROKEN CODE:\n{original_code}\n\n"
        "Please fix the PlantUML syntax and output ONLY the corrected code "
        "between @startuml and @enduml. Do NOT include any explanation text. "
        "Output ONLY valid PlantUML code."
    )
    target_model = getattr(config, "MODEL_ROUTING", {}).get(
        analysis_type, config.LLM_MODEL
    )
    log.info("Asking %s to fix syntax error: %s", target_model, error_msg)
    raw = generate(repair_prompt, model=target_model)
    return _extract_plantuml(raw)


def _test_render_kroki(code: str) -> Tuple[bool, str]:
    """
    Quick test-render via Kroki to check if PlantUML syntax is valid.
    Returns (is_renderable: bool, error_message: str).
    """
    import requests as _req
    import json as _json
    try:
        payload = _json.dumps({"diagram_source": code})
        r = _req.post(
            "https://kroki.io/plantuml/png",
            headers={"Content-Type": "application/json"},
            data=payload,
            timeout=15,
        )
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            return True, ""
        error_text = r.text[:200] if r.text else f"HTTP {r.status_code}"
        return False, error_text
    except Exception as e:
        # Network error — log warning and assume it might render
        log.warning("Kroki unavailable (offline?): %s. Skipping render check.", e)
        return True, ""


def _extract_and_validate(raw_llm_output: str,
                          analysis_type: str = "general") -> str:
    """
    Full pipeline: extract → repair → validate → test-render → retry (max 3 times).
    """
    # Step 1: Extract
    code = _extract_plantuml(raw_llm_output)

    # Step 2: Always run repair (it's idempotent on valid code)
    code = _repair_plantuml(code)

    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        # Step 3: Local validation (type-aware)
        is_valid, error = _validate_plantuml(code, analysis_type)
        if not is_valid:
            log.warning("Local validation failed for %s (attempt %d): %s", analysis_type, attempt + 1, error)
            try:
                raw_retry = _retry_with_llm(code, error, analysis_type)
                code = _repair_plantuml(raw_retry)
                continue  # Go to next attempt to validate/test again
            except Exception as e:
                log.error("LLM retry error for %s: %s", analysis_type, e)
                break

        # Step 4: If local validation passes, test-render via Kroki
        renderable, render_error = _test_render_kroki(code)
        if renderable:
            if attempt > 0:
                log.info("LLM retry fixed Kroki rendering for %s", analysis_type)
            return _inject_skinparam(code)

        log.warning("Kroki test-render failed for %s (attempt %d): %s", analysis_type, attempt + 1, render_error)

        # Step 5: If test-rendering fails, retry with LLM sending the error
        try:
            raw_retry = _retry_with_llm(code, render_error, analysis_type)
            code = _repair_plantuml(raw_retry)
        except Exception as e:
            log.error("LLM retry error for %s: %s", analysis_type, e)
            break

    # If we exhaust retries or break early (Exception), return best effort
    log.warning("Exhausted retries or encountered error for %s. Returning best effort.", analysis_type)
    return _inject_skinparam(code)
