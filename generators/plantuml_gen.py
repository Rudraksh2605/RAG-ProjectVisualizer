"""
PlantUML diagram generators — IR-based pipeline.

Architecture (new):
  1. LLM generates structured JSON matching an IR schema.
  2. Python validates the IR.
  3. Python deterministically compiles the IR into valid PlantUML.
  4. Rendering happens only after deterministic compilation.
  5. Retries repair the IR (re-request JSON), not raw PlantUML.

The old regex-repair path is preserved as a fallback behind
USE_LEGACY_PIPELINE for transition safety, but the default path
is now: prompt → JSON → validate IR → compile → skinparam → render.
"""

import json
import re
import logging
from typing import Dict, Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from core import rag_engine
from core.ollama_client import generate
from generators.uml_ir import parse_ir, IR_CLASSES
from generators.uml_compiler import compile_ir
from generators.uml_validator import validate_ir, validate_compiled_plantuml
from generators.uml_normalizer import normalize_ir
from generators.uml_prompts import IR_SCHEMAS, IR_TASK_INSTRUCTIONS
import config

log = logging.getLogger("plantuml")

# ── Feature flag: set True to use old regex-repair pipeline ────
USE_LEGACY_PIPELINE = False


# ═══════════════════════════════════════════════════════════════
#  Diagram specifications — single source of truth
# ═══════════════════════════════════════════════════════════════

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
            "including callbacks and guards."
        ),
        "query_focused": (
            "Show the lifecycle states and transitions for '{focus}', "
            "including entry/exit actions and event guards."
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
            "Focus on actions the user can take (e.g., 'Take a Quiz', 'View Profile') "
            "rather than just listing UI screens."
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
            "and button click handlers that navigate to other screens."
        ),
        "has_focus": False,
        "top_k": 40,
        "layer_filter": "UI",
    },
}


# ═══════════════════════════════════════════════════════════════
#  Registry — maps display names to (generator_func, needs_focus)
# ═══════════════════════════════════════════════════════════════

DIAGRAM_REGISTRY = {}  # populated at module bottom


# ═══════════════════════════════════════════════════════════════
#  Diagram cache
# ═══════════════════════════════════════════════════════════════

_diagram_cache: Dict[tuple, str] = {}


def _cache_key(diagram_type: str, focus: Optional[str], target_model: Optional[str] = None) -> tuple:
    fp = getattr(rag_engine, "_project_fingerprint", None)
    return (diagram_type, focus or "", fp or "", target_model or "")


def clear_diagram_cache():
    """Clear all cached diagrams (call after re-indexing)."""
    _diagram_cache.clear()
    log.info("Diagram cache cleared")


# ═══════════════════════════════════════════════════════════════
#  Skinparam injection (shared by both pipelines)
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

_RE_SKINPARAM_LINE = re.compile(
    r'^\s*skinparam\s+(\S+)\s+(.+)$', re.IGNORECASE | re.MULTILINE
)


def _inject_skinparam(code: str) -> str:
    """Inject default skinparams into PlantUML code."""
    skinparam_lines = [f"skinparam {k} {v}" for k, v in _DEFAULT_SKINPARAMS.items()]
    skinparam_block = "\n".join(skinparam_lines)

    # Remove any existing skinparam lines (shouldn't be any from compiler, but safety)
    cleaned = _RE_SKINPARAM_LINE.sub("", code)
    cleaned = re.sub(
        r'skinparam\s+\w+\s*\{[^}]*\}',
        '', cleaned, flags=re.IGNORECASE | re.DOTALL,
    )

    return cleaned.replace(
        "@startuml",
        f"@startuml\n{skinparam_block}",
        1,
    )


# ═══════════════════════════════════════════════════════════════
#  NEW PIPELINE: IR-based generation
# ═══════════════════════════════════════════════════════════════

# UML-specific generation settings (lower temperature for syntax-critical tasks)
_UML_TEMPERATURE = 0.15
_UML_TOP_P = 0.85
_UML_MAX_TOKENS = 3072

MAX_IR_RETRIES = 3


def _build_ir_prompt(question: str, context: str, diagram_type: str,
                     model_name: str = "AI Assistant") -> str:
    """
    Build a prompt that asks the LLM to return structured JSON for a diagram.

    No <thinking> blocks. No PlantUML. No markdown fences. Just JSON.
    """
    schema = IR_SCHEMAS.get(diagram_type, "")
    task_instruction = IR_TASK_INSTRUCTIONS.get(diagram_type, "")

    return (
        f"You are {model_name}, an expert AI assistant specialized in Android "
        "code analysis and software architecture.\n\n"
        "You have been given RELEVANT EXCERPTS from the project's codebase via "
        "a retrieval system. Use ONLY the provided context to answer.\n\n"
        f"TASK: {task_instruction}\n\n"
        "CRITICAL RULES:\n"
        "- Think silently. Do NOT include any reasoning, explanation, or commentary.\n"
        "- Return ONLY a single valid JSON object.\n"
        "- Do NOT wrap the JSON in markdown fences (no ```).\n"
        "- Do NOT include any text before or after the JSON.\n"
        "- Do NOT add keys not in the schema.\n"
        "- Relationship endpoints should match declared entity names when possible.\n"
        "- External collaborators (libraries, frameworks) may be listed in the "
        "external_classes or external_components array if the schema supports it.\n"
        "- Use only ASCII characters in names and identifiers.\n\n"
        f"REQUIRED JSON SCHEMA:\n{schema}\n\n"
        f"RETRIEVED CODE CONTEXT:\n{'=' * 60}\n{context}\n{'=' * 60}\n\n"
        f"QUESTION: {question}\n\n"
        "JSON OUTPUT:\n"
    )


def _build_ir_retry_prompt(bad_json: str, errors: List[str],
                           diagram_type: str) -> str:
    """
    Build a retry prompt asking the LLM to fix its JSON output.
    """
    schema = IR_SCHEMAS.get(diagram_type, "")
    error_list = "\n".join(f"  - {e}" for e in errors)

    return (
        "Your previous JSON output had validation errors. Fix them.\n\n"
        "CRITICAL RULES:\n"
        "- Return ONLY the corrected JSON object.\n"
        "- Do NOT include any reasoning, explanation, or commentary.\n"
        "- Do NOT wrap in markdown fences.\n"
        "- Every name in relationships/transitions MUST match a declared entity.\n\n"
        f"VALIDATION ERRORS:\n{error_list}\n\n"
        f"REQUIRED JSON SCHEMA:\n{schema}\n\n"
        f"YOUR BROKEN JSON:\n{bad_json}\n\n"
        "CORRECTED JSON:\n"
    )


def _extract_json(raw_text: str) -> Optional[dict]:
    """
    Extract a JSON object from LLM output.

    Handles common LLM quirks: markdown fences, <think> blocks, trailing text.
    """
    if not raw_text or not raw_text.strip():
        return None

    text = raw_text.strip()

    # Strip <think>...</think> blocks (deepseek-coder, qwen2.5-coder)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Also handle unclosed <think> (model hit token limit mid-thought)
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    text = text.strip()

    # Remove markdown fences if present
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.strip()

    # Remove any text before the first {
    brace_idx = text.find('{')
    if brace_idx == -1:
        log.warning("No '{' found in LLM output after stripping think/fences")
        return None
    text = text[brace_idx:]

    # Remove any text after the last }
    last_brace = text.rfind('}')
    if last_brace == -1:
        return None
    text = text[:last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("JSON parse error: %s", e)
        # Try to fix common issues
        # Fix trailing commas (common LLM mistake)
        fixed = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # Try removing single-line comments (// ...)
            fixed2 = re.sub(r'//[^\n]*', '', fixed)
            try:
                return json.loads(fixed2)
            except json.JSONDecodeError:
                log.warning("JSON still invalid after all fixup attempts")
                return None


def _generate_via_ir(diagram_type: str, question: str,
                     spec: dict, target_model: Optional[str]) -> str:
    """
    Main IR pipeline: prompt → JSON → validate → compile → skinparam.

    Returns PlantUML code string.
    """
    # Step 1: Retrieve code context via RAG (reusing existing infrastructure)
    from core import rag_engine, embeddings, vector_store

    if target_model is None:
        target_model = getattr(config, "MODEL_ROUTING", {}).get(
            diagram_type, config.LLM_MODEL
        )

    # Build the context the same way rag_engine does
    expanded = rag_engine.expand_query(question, target_model)
    q_emb = embeddings.embed_text(expanded)

    where = {}
    if spec.get("layer_filter"):
        where["layer"] = spec["layer_filter"]

    results = vector_store.search(
        q_emb,
        top_k=spec.get("top_k", config.RAG_TOP_K),
        where=where if where else None,
    )
    context = rag_engine._format_retrieved_context(results)

    # Step 2: Build prompt asking for JSON IR
    prompt = _build_ir_prompt(question, context, diagram_type, target_model)

    log.info("[IR Pipeline] Generating %s via %s", diagram_type, target_model)

    # Step 3: Generate with lower temperature + JSON format mode
    raw = generate(
        prompt,
        model=target_model,
        temperature=_UML_TEMPERATURE,
        max_tokens=_UML_MAX_TOKENS,
        format_json=True,
    )

    log.info("[IR Pipeline] Raw LLM output (first 500 chars): %.500s", raw)

    # Step 4: Extract → Parse → Validate → Compile (with retries)
    last_errors: List[str] = []

    for attempt in range(MAX_IR_RETRIES):
        # Extract JSON from LLM output
        data = _extract_json(raw)
        if data is None:
            last_errors = ["Failed to extract valid JSON from LLM output"]
            log.warning("[IR Pipeline] JSON extraction failed (attempt %d). Raw (first 300 chars): %.300s", attempt + 1, raw)
            if attempt < MAX_IR_RETRIES - 1:
                retry_prompt = _build_ir_retry_prompt(
                    raw[:2000], last_errors, diagram_type
                )
                raw = generate(
                    retry_prompt, model=target_model,
                    temperature=_UML_TEMPERATURE, max_tokens=_UML_MAX_TOKENS,
                    format_json=True,
                )
                continue
            break

        # Parse into IR dataclass
        try:
            ir = parse_ir(diagram_type, data)
        except Exception as e:
            last_errors = [f"IR parsing error: {e}"]
            log.warning("[IR Pipeline] IR parse failed (attempt %d): %s", attempt + 1, e)
            if attempt < MAX_IR_RETRIES - 1:
                retry_prompt = _build_ir_retry_prompt(
                    json.dumps(data, indent=2)[:2000], last_errors, diagram_type
                )
                raw = generate(
                    retry_prompt, model=target_model,
                    temperature=_UML_TEMPERATURE, max_tokens=_UML_MAX_TOKENS,
                )
                continue
            break

        # Normalize IR (deterministic transformations before validation)
        try:
            parsed_data = rag_engine.get_parsed_files()
            ir = normalize_ir(diagram_type, ir, parsed_data)
        except Exception as e:
            log.warning("[IR Pipeline] Normalization failed (attempt %d): %s", attempt + 1, e)
            # Non-fatal: proceed with un-normalized IR

        # Validate IR
        is_valid, ir_errors = validate_ir(diagram_type, ir)
        if not is_valid:
            last_errors = ir_errors
            log.warning("[IR Pipeline] IR validation failed (attempt %d): %s",
                       attempt + 1, ir_errors)
            if attempt < MAX_IR_RETRIES - 1:
                retry_prompt = _build_ir_retry_prompt(
                    json.dumps(data, indent=2)[:2000], ir_errors, diagram_type
                )
                raw = generate(
                    retry_prompt, model=target_model,
                    temperature=_UML_TEMPERATURE, max_tokens=_UML_MAX_TOKENS,
                )
                continue
            break

        # Compile IR → PlantUML
        try:
            plantuml_code = compile_ir(diagram_type, ir)
        except Exception as e:
            last_errors = [f"Compilation error: {e}"]
            log.error("[IR Pipeline] Compilation failed: %s", e)
            break

        # Post-compile validation
        pc_valid, pc_errors = validate_compiled_plantuml(plantuml_code, diagram_type)
        if not pc_valid:
            log.warning("[IR Pipeline] Post-compile validation issues: %s", pc_errors)
            # Non-fatal: compiler output should be mostly correct

        # Success!
        log.info("[IR Pipeline] %s generated successfully (attempt %d)", diagram_type, attempt + 1)
        return _inject_skinparam(plantuml_code)

    # All retries exhausted — return error diagram
    error_detail = "; ".join(last_errors) if last_errors else "Unknown error"
    log.error("[IR Pipeline] Failed after %d attempts for %s: %s",
              MAX_IR_RETRIES, diagram_type, error_detail)
    return _inject_skinparam(
        f"@startuml\n"
        f"title \"Generation Failed — {diagram_type}\"\n"
        f"note \"IR pipeline failed after {MAX_IR_RETRIES} attempts.\\n"
        f"Errors: {error_detail[:200]}\" as N1\n"
        f"@enduml"
    )


# ═══════════════════════════════════════════════════════════════
#  LEGACY PIPELINE: regex-based extract/repair/validate
#  Kept as fallback; activated only if USE_LEGACY_PIPELINE = True
# ═══════════════════════════════════════════════════════════════

_PUML_BLOCK_RE = re.compile(r'@startuml.*?@enduml', re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r'```(?:plantuml|puml|uml)?\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)

_ERROR_MARKERS = [
    "[Ollama error", "[Streaming error", "I cannot generate",
    "I'm sorry", "I apologize", "As an AI",
]

_TYPE_MARKERS = {
    "class_diagram": ["class "],
    "sequence_diagram": ["participant ", "actor ", "->"],
    "activity_diagram": ["start", ":"],
    "state_diagram": ["state ", "[*]"],
    "component_diagram": ["component ", "["],
    "usecase_diagram": ["usecase ", "actor "],
    "package_diagram": ["package "],
    "deployment_diagram": ["node ", "database ", "cloud "],
    "navigation_diagram": ["state ", "[*]"],
}

_COMMENTARY_PREFIXES = (
    "here is", "here's", "below is", "this diagram",
    "note:", "explanation:", "the above", "as you can see",
    "i hope", "let me", "please note", "sure,",
)


def _extract_plantuml(text: str) -> str:
    """Extract PlantUML block from raw LLM output (legacy)."""
    if not text or not text.strip():
        return "@startuml\n' Empty diagram\n@enduml"
    matches = _PUML_BLOCK_RE.findall(text)
    if matches:
        return max(matches, key=len).strip()
    fence_matches = _CODE_FENCE_RE.findall(text)
    if fence_matches:
        body = max(fence_matches, key=len).strip()
        inner = _PUML_BLOCK_RE.findall(body)
        if inner:
            return max(inner, key=len).strip()
        return f"@startuml\n{body}\n@enduml"
    return f"@startuml\n{text.strip()}\n@enduml"


def _validate_plantuml_legacy(code: str, diagram_type: str = "general") -> Tuple[bool, str]:
    """Heuristic validation (legacy)."""
    if not code or len(code.strip()) < 20:
        return False, "PlantUML code is too short or empty"
    if "@startuml" not in code:
        return False, "Missing @startuml tag"
    if "@enduml" not in code:
        return False, "Missing @enduml tag"
    start = code.index("@startuml") + len("@startuml")
    end = code.index("@enduml")
    body = code[start:end].strip()
    if not body:
        return False, "Diagram body is empty"
    open_b = body.count("{")
    close_b = body.count("}")
    if open_b != close_b:
        return False, f"Unbalanced braces: {open_b} open vs {close_b} close"
    markers = _TYPE_MARKERS.get(diagram_type, [])
    if markers:
        body_lower = body.lower()
        if not any(m.lower() in body_lower for m in markers):
            return False, f"Missing expected keywords for {diagram_type}"
    return True, ""


def _repair_plantuml(code: str) -> str:
    """Regex-based auto-repair (legacy)."""
    if "@startuml" not in code:
        code = "@startuml\n" + code
    if "@enduml" not in code:
        code = code + "\n@enduml"
    # Remove duplicate tags
    code = re.sub(r'(@startuml\s*\n?){2,}', '@startuml\n', code, flags=re.IGNORECASE)
    code = re.sub(r'(@enduml\s*\n?){2,}', '@enduml', code, flags=re.IGNORECASE)
    # Strip skinparams
    code = _RE_SKINPARAM_LINE.sub("", code)
    code = re.sub(r'skinparam\s+\w+\s*\{[^}]*\}', '', code, flags=re.IGNORECASE | re.DOTALL)
    # Remove markdown
    code = code.replace("```", "")
    # Fix braces
    start = code.index("@startuml")
    end = code.index("@enduml") + len("@enduml")
    header = code[start:start + len("@startuml")]
    footer = "@enduml"
    body = code[start + len("@startuml"):end - len("@enduml")]
    ob = body.count("{")
    cb = body.count("}")
    if ob > cb:
        body = body.rstrip() + "\n" + ("}\n" * (ob - cb))
    # Remove commentary
    cleaned = []
    for line in body.split("\n"):
        stripped = line.strip().lower()
        if any(stripped.startswith(p) for p in _COMMENTARY_PREFIXES):
            continue
        cleaned.append(line)
    body = "\n".join(cleaned)
    return f"{header}\n{body.strip()}\n{footer}"


def _legacy_extract_and_validate(raw: str, diagram_type: str) -> str:
    """Legacy pipeline: extract → repair → validate → skinparam."""
    code = _extract_plantuml(raw)
    code = _repair_plantuml(code)
    is_valid, error = _validate_plantuml_legacy(code, diagram_type)
    if not is_valid:
        log.warning("[Legacy] Validation failed for %s: %s", diagram_type, error)
    return _inject_skinparam(code)


# ═══════════════════════════════════════════════════════════════
#  Unified generator entry point
# ═══════════════════════════════════════════════════════════════

def generate_diagram(diagram_type: str, focus: Optional[str] = None,
                     target_model: str = None, force: bool = False) -> str:
    """
    Generate a PlantUML diagram of the given type.

    Uses the IR pipeline by default. Falls back to legacy if USE_LEGACY_PIPELINE is set.
    """
    key = _cache_key(diagram_type, focus, target_model)
    if not force and key in _diagram_cache:
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

    if USE_LEGACY_PIPELINE or diagram_type not in IR_CLASSES:
        # Legacy path: LLM generates PlantUML directly
        raw = rag_engine.query(
            question,
            analysis_type=diagram_type,
            top_k=spec.get("top_k", config.RAG_TOP_K),
            layer_filter=spec.get("layer_filter"),
            target_model=target_model,
        )
        result = _legacy_extract_and_validate(raw, diagram_type)
    else:
        # NEW path: LLM generates JSON IR → compile → PlantUML
        result = _generate_via_ir(diagram_type, question, spec, target_model)

    _diagram_cache[key] = result
    log.info("Generated and cached %s (focus=%s)", diagram_type, focus)
    return result


# ═══════════════════════════════════════════════════════════════
#  Backward-compatible convenience wrappers
# ═══════════════════════════════════════════════════════════════

def generate_class_diagram(focus_class: str = None, target_model: str = None, force: bool = False) -> str:
    return generate_diagram("class_diagram", focus_class, target_model, force)

def generate_sequence_diagram(focus: str = None, target_model: str = None, force: bool = False) -> str:
    return generate_diagram("sequence_diagram", focus, target_model, force)

def generate_activity_diagram(target_model: str = None, force: bool = False) -> str:
    return generate_diagram("activity_diagram", target_model=target_model, force=force)

def generate_state_diagram(focus_class: str = None, target_model: str = None, force: bool = False) -> str:
    return generate_diagram("state_diagram", focus_class, target_model, force)

def generate_component_diagram(target_model: str = None, force: bool = False) -> str:
    return generate_diagram("component_diagram", target_model=target_model, force=force)

def generate_usecase_diagram(target_model: str = None, force: bool = False) -> str:
    return generate_diagram("usecase_diagram", target_model=target_model, force=force)

def generate_package_diagram(target_model: str = None, force: bool = False) -> str:
    return generate_diagram("package_diagram", target_model=target_model, force=force)

def generate_deployment_diagram(target_model: str = None, force: bool = False) -> str:
    return generate_diagram("deployment_diagram", target_model=target_model, force=force)

def generate_navigation_diagram(target_model: str = None, force: bool = False) -> str:
    return generate_diagram("navigation_diagram", target_model=target_model, force=force)


# ═══════════════════════════════════════════════════════════════
#  Populate DIAGRAM_REGISTRY
# ═══════════════════════════════════════════════════════════════

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
#  Parallel generation
# ═══════════════════════════════════════════════════════════════

def generate_diagrams_parallel(
    diagram_types: List[str],
    focus_map: Optional[Dict[str, str]] = None,
    target_model: str = None,
) -> Dict[str, str]:
    """Generate multiple diagrams in parallel."""
    focus_map = focus_map or {}
    results = {}
    max_workers = getattr(config, "PARALLEL_MAX_WORKERS", 3)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(generate_diagram, dt, focus_map.get(dt), target_model): dt
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
