"""
PlantUML diagram generators.

Default flow:
1. Retrieve relevant project context.
2. Ask the LLM for structured JSON IR.
3. Normalize and validate the IR against UML-specific rules.
4. Compile deterministically to PlantUML.
5. Repair lightweight syntax issues and validate the compiled PlantUML.
6. Retry JSON generation if anything remains invalid.

The legacy raw-PlantUML path is kept behind a feature flag for fallback only.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import config
from core import rag_engine
from core.ollama_client import generate
from generators.uml_compiler import compile_ir
from generators.uml_ir import IR_CLASSES, parse_ir
from generators.uml_normalizer import extract_screens_from_parsed_data, normalize_ir
from generators.uml_prompts import IR_DIAGRAM_RULES, IR_SCHEMAS, IR_TASK_INSTRUCTIONS
from generators.uml_validator import validate_compiled_plantuml, validate_ir

log = logging.getLogger("plantuml")

USE_LEGACY_PIPELINE = False


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
        "context_budget_chars": 9000,
        "max_tokens": 1600,
    },
    "sequence_diagram": {
        "display_name": "Sequence Diagram",
        "query_default": (
            "Show the most important user interaction flow in this project with the "
            "runtime participants, messages, and one meaningful branch if present."
        ),
        "query_focused": (
            "Show the flow when '{focus}' is triggered, including the participants, "
            "messages, and one request-response round-trip."
        ),
        "has_focus": True,
        "top_k": 15,
        "context_budget_chars": 10000,
        "max_tokens": 1800,
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
        "context_budget_chars": 8000,
        "max_tokens": 1400,
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
        "context_budget_chars": 9000,
        "max_tokens": 1500,
    },
    "component_diagram": {
        "display_name": "Component Diagram",
        "query_default": (
            "Show the app's major components grouped by feature area, "
            "their stereotypes, and how they connect."
        ),
        "has_focus": False,
        "top_k": 15,
        "context_budget_chars": 10000,
        "max_tokens": 1700,
    },
    "usecase_diagram": {
        "display_name": "Use Case Diagram",
        "query_default": (
            "Identify the external actors and the user goals they achieve with this app. "
            "Focus on business capabilities and user actions, not UI screen names or code classes."
        ),
        "has_focus": False,
        "top_k": 30,
        "context_budget_chars": 12000,
        "max_tokens": 2200,
    },
    "package_diagram": {
        "display_name": "Package Diagram",
        "query_default": (
            "Show the 3-4 architectural layers or feature packages, 2-3 key classes in each, "
            "and inter-layer dependencies."
        ),
        "has_focus": False,
        "top_k": 15,
        "context_budget_chars": 9000,
        "max_tokens": 1600,
    },
    "deployment_diagram": {
        "display_name": "Deployment Diagram",
        "query_default": (
            "Show the Android device, external cloud services, API servers, databases, "
            "and their runtime connection protocols."
        ),
        "has_focus": False,
        "top_k": 15,
        "context_budget_chars": 8500,
        "max_tokens": 1500,
    },
    "navigation_diagram": {
        "display_name": "Navigation Diagram",
        "query_default": (
            "List every Activity and Fragment in this project. For each one, list all "
            "navigation actions, intent launches, fragment transitions, and click handlers "
            "that move to another screen."
        ),
        "has_focus": False,
        "top_k": 40,
        "layer_filter": "UI",
        "context_budget_chars": 14000,
        "max_tokens": 2600,
    },
}


DIAGRAM_REGISTRY = {}
_diagram_cache: Dict[tuple, str] = {}


def _cache_key(diagram_type: str, focus: Optional[str], target_model: Optional[str] = None) -> tuple:
    fingerprint = getattr(rag_engine, "_project_fingerprint", None)
    return (diagram_type, focus or "", fingerprint or "", target_model or "")


def clear_diagram_cache():
    _diagram_cache.clear()
    log.info("Diagram cache cleared")


_DEFAULT_SKINPARAMS = {
    "defaultFontName": '"Segoe UI"',
    "defaultFontSize": "13",
    "shadowing": "false",
    "roundCorner": "10",
    "BackgroundColor": "#FEFEFE",
    "ArrowColor": "#1565C0",
    "ArrowFontColor": "#333333",
    "ArrowFontSize": "12",
    "ArrowThickness": "1.5",
    "noteBorderColor": "#FFB300",
    "noteBackgroundColor": "#FFF9C4",
    "noteFontColor": "#333333",
    "titleFontSize": "18",
    "titleFontColor": "#1A1A2E",
    "titleFontStyle": "bold",
    "ClassBackgroundColor": "#E3F2FD",
    "ClassBorderColor": "#1976D2",
    "ClassFontColor": "#1A1A2E",
    "ClassAttributeFontColor": "#37474F",
    "ClassStereotypeFontColor": "#7B1FA2",
    "PackageBackgroundColor": "#F3E5F5",
    "PackageBorderColor": "#7B1FA2",
    "PackageFontColor": "#4A148C",
    "ComponentBackgroundColor": "#E8F5E9",
    "ComponentBorderColor": "#388E3C",
    "ComponentFontColor": "#1B5E20",
    "UsecaseBackgroundColor": "#E3F2FD",
    "UsecaseBorderColor": "#1565C0",
    "UsecaseFontColor": "#0D47A1",
    "ActorBorderColor": "#1565C0",
    "ActorFontColor": "#1A1A2E",
    "StateBackgroundColor": "#E8EAF6",
    "StateBorderColor": "#283593",
    "StateFontColor": "#1A237E",
    "ParticipantBackgroundColor": "#E3F2FD",
    "ParticipantBorderColor": "#1565C0",
    "ParticipantFontColor": "#0D47A1",
    "DatabaseBackgroundColor": "#FFF3E0",
    "DatabaseBorderColor": "#E65100",
    "DatabaseFontColor": "#BF360C",
    "CloudBackgroundColor": "#E0F7FA",
    "CloudBorderColor": "#00838F",
    "CloudFontColor": "#006064",
    "NodeBackgroundColor": "#F3E5F5",
    "NodeBorderColor": "#6A1B9A",
    "NodeFontColor": "#4A148C",
    "SequenceLifeLineBorderColor": "#1565C0",
    "SequenceGroupBackgroundColor": "#E8EAF6",
}

_RE_SKINPARAM_LINE = re.compile(r"^\s*skinparam\s+(\S+)\s+(.+)$", re.IGNORECASE | re.MULTILINE)


def _inject_skinparam(code: str) -> str:
    skinparam_lines = [f"skinparam {key} {value}" for key, value in _DEFAULT_SKINPARAMS.items()]
    skinparam_block = "\n".join(skinparam_lines)
    cleaned = _RE_SKINPARAM_LINE.sub("", code)
    cleaned = re.sub(r"skinparam\s+\w+\s*\{[^}]*\}", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.replace("@startuml", f"@startuml\n{skinparam_block}", 1)


_UML_TEMPERATURE = 0.15
_UML_TOP_P = 0.85
_UML_MAX_TOKENS = 3072
MAX_IR_RETRIES = 3


def _is_deepseek_model(model_name: Optional[str]) -> bool:
    return "deepseek" in (model_name or "").lower()


def _effective_uml_context_budget(spec: dict, model_name: Optional[str]) -> int:
    budget = spec.get("context_budget_chars", config.UML_CONTEXT_MAX_CHARS)
    if _is_deepseek_model(model_name):
        budget = min(budget, config.DEEPSEEK_UML_CONTEXT_MAX_CHARS)
    return budget


def _effective_uml_max_tokens(spec: dict, model_name: Optional[str]) -> int:
    token_budget = spec.get("max_tokens", _UML_MAX_TOKENS)
    if _is_deepseek_model(model_name):
        token_budget = min(token_budget, config.DEEPSEEK_UML_MAX_TOKENS)
    return token_budget


def _effective_uml_context_size(model_name: Optional[str]) -> int:
    if _is_deepseek_model(model_name):
        return config.DEEPSEEK_UML_CONTEXT_SIZE
    return config.LLM_CONTEXT_SIZE


def _uses_native_json_mode(model_name: Optional[str]) -> bool:
    if _is_deepseek_model(model_name):
        return config.DEEPSEEK_USE_NATIVE_JSON_MODE
    return True


def _build_ir_prompt(
    question: str,
    context: str,
    diagram_type: str,
    model_name: str = "AI Assistant",
    extra_hints: str = "",
) -> str:
    schema = IR_SCHEMAS.get(diagram_type, "")
    task_instruction = IR_TASK_INSTRUCTIONS.get(diagram_type, "")
    diagram_rules = IR_DIAGRAM_RULES.get(diagram_type, "")

    return (
        f"You are {model_name}, an expert AI assistant specialized in Android "
        "code analysis and software architecture.\n\n"
        "You have been given relevant excerpts from the project's codebase via "
        "a retrieval system. Use only the provided context.\n\n"
        f"TASK:\n{task_instruction}\n\n"
        f"DIAGRAM DEFINITION AND MODELING RULES:\n{diagram_rules}\n\n"
        "CRITICAL RULES:\n"
        "- Think silently. Do not include reasoning or commentary.\n"
        "- Return only a single valid JSON object.\n"
        "- Do not wrap the JSON in markdown fences.\n"
        "- Do not include any text before or after the JSON.\n"
        "- Do not add keys not in the schema.\n"
        "- Relationship endpoints should match declared entity names.\n"
        "- Use the selected UML diagram type exactly; do not drift into another diagram view.\n"
        "- External collaborators may be listed only in external arrays when the schema supports them.\n"
        "- Use only ASCII characters in names and identifiers.\n\n"
        f"REQUIRED JSON SCHEMA:\n{schema}\n\n"
        f"{extra_hints}"
        f"RETRIEVED CODE CONTEXT:\n{'=' * 60}\n{context}\n{'=' * 60}\n\n"
        f"QUESTION:\n{question}\n\n"
        "JSON OUTPUT:\n"
    )


def _build_ir_retry_prompt(
    bad_json: str,
    errors: List[str],
    diagram_type: str,
    compiled_code: str = "",
) -> str:
    schema = IR_SCHEMAS.get(diagram_type, "")
    diagram_rules = IR_DIAGRAM_RULES.get(diagram_type, "")
    error_list = "\n".join(f"  - {error}" for error in errors)
    compiled_section = (
        f"COMPILED PLANTUML THAT FAILED VALIDATION:\n{compiled_code}\n\n"
        if compiled_code else ""
    )

    return (
        "Your previous JSON output had validation errors. Fix it.\n\n"
        f"DIAGRAM DEFINITION AND MODELING RULES:\n{diagram_rules}\n\n"
        "CRITICAL RULES:\n"
        "- Return only the corrected JSON object.\n"
        "- Do not include reasoning or commentary.\n"
        "- Do not wrap in markdown fences.\n"
        "- Every reference in relationships or transitions must match a declared entity.\n"
        "- Fix diagram-type mistakes, not just missing fields.\n\n"
        f"VALIDATION ERRORS:\n{error_list}\n\n"
        f"REQUIRED JSON SCHEMA:\n{schema}\n\n"
        f"{compiled_section}"
        f"YOUR BROKEN JSON:\n{bad_json}\n\n"
        "CORRECTED JSON:\n"
    )


def _build_prompt_hints(diagram_type: str) -> str:
    if diagram_type != "navigation_diagram":
        return ""

    parsed_data = rag_engine.get_parsed_files()
    if not parsed_data:
        return ""

    screens = extract_screens_from_parsed_data(parsed_data)
    if not screens:
        return ""

    screen_names = ", ".join(screen.name for screen in screens[:40])
    return f"KNOWN SCREENS DETECTED FROM STATIC PARSING:\n{screen_names}\n\n"


def _extract_json(raw_text: str) -> Optional[dict]:
    if not raw_text or not raw_text.strip():
        return None

    text = raw_text.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    brace_index = text.find("{")
    if brace_index == -1:
        log.warning("No JSON object start found in LLM output")
        return None
    text = text[brace_index:]

    last_brace = text.rfind("}")
    if last_brace == -1:
        return None
    text = text[: last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        log.warning("JSON parse error: %s", error)
        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            fixed = re.sub(r"//[^\n]*", "", fixed)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                log.warning("JSON still invalid after fixup attempts")
                return None


def _repair_compiled_plantuml(code: str, diagram_type: str) -> str:
    if not code:
        return code

    repaired = code.strip().replace("```", "")
    repaired = re.sub(r"(@startuml\s*){2,}", "@startuml\n", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"(@enduml\s*){2,}", "@enduml\n", repaired, flags=re.IGNORECASE)

    if "@startuml" not in repaired:
        repaired = "@startuml\n" + repaired
    if "@enduml" not in repaired:
        repaired = repaired.rstrip() + "\n@enduml"

    start = repaired.find("@startuml")
    end = repaired.rfind("@enduml")
    if start == -1 or end == -1:
        return repaired

    header = "@startuml"
    footer = "@enduml"
    body = repaired[start + len("@startuml"):end].strip()

    body = re.sub(
        r"\bnote\s+(right|left|top|bottom)\s+of\s*:\s*",
        r"note \1 : ",
        body,
        flags=re.IGNORECASE,
    )

    open_braces = body.count("{")
    close_braces = body.count("}")
    if open_braces > close_braces:
        body = body.rstrip() + "\n" + ("}\n" * (open_braces - close_braces))

    body = re.sub(r"\n{3,}", "\n\n", body)
    return f"{header}\n{body}\n{footer}"


def _build_failure_diagram(diagram_type: str) -> str:
    return _inject_skinparam(
        "@startuml\n"
        f'title "Unable to Generate {diagram_type}"\n'
        'note "Automatic repair could not finish this diagram yet. '
        'Please retry after re-indexing or refining the project context." as N1\n'
        "@enduml"
    )


def _generate_via_ir(diagram_type: str, question: str, spec: dict, target_model: Optional[str]) -> str:
    if target_model is None:
        target_model = getattr(config, "MODEL_ROUTING", {}).get(diagram_type, config.LLM_MODEL)

    max_tokens = _effective_uml_max_tokens(spec, target_model)
    context_budget_chars = _effective_uml_context_budget(spec, target_model)
    context_size = _effective_uml_context_size(target_model)
    use_native_json_mode = _uses_native_json_mode(target_model)
    context = rag_engine.retrieve_context(
        question,
        analysis_type=diagram_type,
        top_k=spec.get("top_k", config.RAG_TOP_K),
        layer_filter=spec.get("layer_filter"),
        target_model=target_model,
        max_context_chars=context_budget_chars,
    )
    prompt = _build_ir_prompt(
        question,
        context,
        diagram_type,
        target_model,
        extra_hints=_build_prompt_hints(diagram_type),
    )

    log.info(
        "[IR Pipeline] Generating %s via %s (ctx_chars=%d, num_ctx=%d, max_tokens=%d, native_json=%s)",
        diagram_type,
        target_model,
        context_budget_chars,
        context_size,
        max_tokens,
        use_native_json_mode,
    )
    raw = generate(
        prompt,
        model=target_model,
        temperature=_UML_TEMPERATURE,
        max_tokens=max_tokens,
        context_size=context_size,
        format_json=use_native_json_mode,
    )
    log.info("[IR Pipeline] Raw LLM output (first 500 chars): %.500s", raw)

    last_errors: List[str] = []

    for attempt in range(MAX_IR_RETRIES):
        data = _extract_json(raw)
        if data is None:
            last_errors = ["Failed to extract valid JSON from LLM output"]
            log.warning(
                "[IR Pipeline] JSON extraction failed (attempt %d). Raw (first 300 chars): %.300s",
                attempt + 1,
                raw,
            )
            if attempt < MAX_IR_RETRIES - 1:
                raw = generate(
                    _build_ir_retry_prompt(raw[:4000], last_errors, diagram_type),
                    model=target_model,
                    temperature=_UML_TEMPERATURE,
                    max_tokens=max_tokens,
                    context_size=context_size,
                    format_json=use_native_json_mode,
                )
                continue
            break

        try:
            ir = parse_ir(diagram_type, data)
        except Exception as error:
            last_errors = [f"IR parsing error: {error}"]
            log.warning("[IR Pipeline] IR parse failed (attempt %d): %s", attempt + 1, error)
            if attempt < MAX_IR_RETRIES - 1:
                raw = generate(
                    _build_ir_retry_prompt(json.dumps(data, indent=2)[:4000], last_errors, diagram_type),
                    model=target_model,
                    temperature=_UML_TEMPERATURE,
                    max_tokens=max_tokens,
                    context_size=context_size,
                    format_json=use_native_json_mode,
                )
                continue
            break

        try:
            ir = normalize_ir(diagram_type, ir, rag_engine.get_parsed_files())
        except Exception as error:
            log.warning("[IR Pipeline] Normalization failed (attempt %d): %s", attempt + 1, error)

        is_valid, ir_errors = validate_ir(diagram_type, ir)
        if not is_valid:
            last_errors = ir_errors
            log.warning("[IR Pipeline] IR validation failed (attempt %d): %s", attempt + 1, ir_errors)
            if attempt < MAX_IR_RETRIES - 1:
                raw = generate(
                    _build_ir_retry_prompt(json.dumps(data, indent=2)[:4000], ir_errors, diagram_type),
                    model=target_model,
                    temperature=_UML_TEMPERATURE,
                    max_tokens=max_tokens,
                    context_size=context_size,
                    format_json=use_native_json_mode,
                )
                continue
            break

        try:
            plantuml_code = compile_ir(diagram_type, ir)
        except Exception as error:
            last_errors = [f"Compilation error: {error}"]
            log.error("[IR Pipeline] Compilation failed (attempt %d): %s", attempt + 1, error)
            if attempt < MAX_IR_RETRIES - 1:
                raw = generate(
                    _build_ir_retry_prompt(json.dumps(data, indent=2)[:4000], last_errors, diagram_type),
                    model=target_model,
                    temperature=_UML_TEMPERATURE,
                    max_tokens=max_tokens,
                    context_size=context_size,
                    format_json=use_native_json_mode,
                )
                continue
            break

        repaired_code = _repair_compiled_plantuml(plantuml_code, diagram_type)
        compiled_valid, compiled_errors = validate_compiled_plantuml(repaired_code, diagram_type)
        if not compiled_valid:
            last_errors = compiled_errors
            log.warning(
                "[IR Pipeline] Post-compile validation failed (attempt %d): %s",
                attempt + 1,
                compiled_errors,
            )
            if attempt < MAX_IR_RETRIES - 1:
                raw = generate(
                    _build_ir_retry_prompt(
                        json.dumps(data, indent=2)[:4000],
                        compiled_errors,
                        diagram_type,
                        compiled_code=repaired_code[:4000],
                    ),
                    model=target_model,
                    temperature=_UML_TEMPERATURE,
                    max_tokens=max_tokens,
                    context_size=context_size,
                    format_json=use_native_json_mode,
                )
                continue
            break

        log.info("[IR Pipeline] %s generated successfully (attempt %d)", diagram_type, attempt + 1)
        return _inject_skinparam(repaired_code)

    error_detail = "; ".join(last_errors) if last_errors else "Unknown error"
    log.error("[IR Pipeline] Failed after %d attempts for %s: %s", MAX_IR_RETRIES, diagram_type, error_detail)
    return _build_failure_diagram(diagram_type)


_PUML_BLOCK_RE = re.compile(r"@startuml.*?@enduml", re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```(?:plantuml|puml|uml)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

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
    "here is",
    "here's",
    "below is",
    "this diagram",
    "note:",
    "explanation:",
    "the above",
    "as you can see",
    "i hope",
    "let me",
    "please note",
    "sure,",
)


def _extract_plantuml(text: str) -> str:
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
    if not code or len(code.strip()) < 20:
        return False, "PlantUML code is too short or empty"
    if "@startuml" not in code:
        return False, "Missing @startuml tag"
    if "@enduml" not in code:
        return False, "Missing @enduml tag"

    body = code[code.index("@startuml") + len("@startuml"):code.index("@enduml")].strip()
    if not body:
        return False, "Diagram body is empty"
    if body.count("{") != body.count("}"):
        return False, "Unbalanced braces"

    markers = _TYPE_MARKERS.get(diagram_type, [])
    if markers and not any(marker.lower() in body.lower() for marker in markers):
        return False, f"Missing expected keywords for {diagram_type}"

    return True, ""


def _repair_plantuml_legacy(code: str) -> str:
    if "@startuml" not in code:
        code = "@startuml\n" + code
    if "@enduml" not in code:
        code = code.rstrip() + "\n@enduml"

    code = re.sub(r"(@startuml\s*\n?){2,}", "@startuml\n", code, flags=re.IGNORECASE)
    code = re.sub(r"(@enduml\s*\n?){2,}", "@enduml", code, flags=re.IGNORECASE)
    code = _RE_SKINPARAM_LINE.sub("", code)
    code = re.sub(r"skinparam\s+\w+\s*\{[^}]*\}", "", code, flags=re.IGNORECASE | re.DOTALL)
    code = code.replace("```", "")

    start = code.index("@startuml")
    end = code.index("@enduml") + len("@enduml")
    header = code[start:start + len("@startuml")]
    body = code[start + len("@startuml"):end - len("@enduml")]
    footer = "@enduml"

    open_braces = body.count("{")
    close_braces = body.count("}")
    if open_braces > close_braces:
        body = body.rstrip() + "\n" + ("}\n" * (open_braces - close_braces))

    cleaned_lines = []
    for line in body.splitlines():
        stripped = line.strip().lower()
        if any(stripped.startswith(prefix) for prefix in _COMMENTARY_PREFIXES):
            continue
        cleaned_lines.append(line)
    body = "\n".join(cleaned_lines)

    return f"{header}\n{body.strip()}\n{footer}"


def _legacy_extract_and_validate(raw: str, diagram_type: str) -> str:
    code = _extract_plantuml(raw)
    code = _repair_plantuml_legacy(code)
    is_valid, error = _validate_plantuml_legacy(code, diagram_type)
    if not is_valid:
        log.warning("[Legacy] Validation failed for %s: %s", diagram_type, error)
    return _inject_skinparam(code)


def generate_diagram(
    diagram_type: str,
    focus: Optional[str] = None,
    target_model: str = None,
    force: bool = False,
) -> str:
    key = _cache_key(diagram_type, focus, target_model)
    if not force and key in _diagram_cache:
        log.info("Cache hit for %s (focus=%s)", diagram_type, focus)
        return _diagram_cache[key]

    spec = DIAGRAM_SPECS.get(diagram_type)
    if not spec:
        log.error("Unknown diagram type: %s", diagram_type)
        return "@startuml\n' Unknown diagram type\n@enduml"

    if focus and spec.get("has_focus") and spec.get("query_focused"):
        question = spec["query_focused"].format(focus=focus)
    else:
        question = spec["query_default"]

    if USE_LEGACY_PIPELINE or diagram_type not in IR_CLASSES:
        raw = rag_engine.query(
            question,
            analysis_type=diagram_type,
            top_k=spec.get("top_k", config.RAG_TOP_K),
            layer_filter=spec.get("layer_filter"),
            target_model=target_model,
            max_context_chars=spec.get("context_budget_chars", config.UML_CONTEXT_MAX_CHARS),
        )
        result = _legacy_extract_and_validate(raw, diagram_type)
    else:
        result = _generate_via_ir(diagram_type, question, spec, target_model)

    _diagram_cache[key] = result
    log.info("Generated and cached %s (focus=%s)", diagram_type, focus)
    return result


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


_WRAPPER_MAP = {
    "class_diagram": generate_class_diagram,
    "sequence_diagram": generate_sequence_diagram,
    "activity_diagram": generate_activity_diagram,
    "state_diagram": generate_state_diagram,
    "component_diagram": generate_component_diagram,
    "usecase_diagram": generate_usecase_diagram,
    "package_diagram": generate_package_diagram,
    "deployment_diagram": generate_deployment_diagram,
    "navigation_diagram": generate_navigation_diagram,
}

DIAGRAM_REGISTRY.update({
    spec["display_name"]: (_WRAPPER_MAP[key], spec.get("has_focus", False))
    for key, spec in DIAGRAM_SPECS.items()
})


def generate_diagrams_parallel(
    diagram_types: List[str],
    focus_map: Optional[Dict[str, str]] = None,
    target_model: str = None,
) -> Dict[str, str]:
    focus_map = focus_map or {}
    results: Dict[str, str] = {}
    max_workers = getattr(config, "PARALLEL_MAX_WORKERS", 3)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(generate_diagram, diagram_type, focus_map.get(diagram_type), target_model): diagram_type
            for diagram_type in diagram_types
        }
        for future in as_completed(futures):
            diagram_type = futures[future]
            try:
                results[diagram_type] = future.result()
            except Exception as error:
                log.error("Parallel generation failed for %s: %s", diagram_type, error)
                results[diagram_type] = _build_failure_diagram(diagram_type)

    return results
