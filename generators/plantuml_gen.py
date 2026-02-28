"""
PlantUML diagram generators — class, sequence, activity, state-machine,
component, use-case, package, and deployment diagrams.

All generators use RAG to retrieve relevant code chunks before asking
the LLM to produce PlantUML syntax.

Includes robust extraction, validation, auto-repair, and LLM retry
to ensure rendered diagrams even when the LLM produces imperfect syntax.
"""

import re
from core import rag_engine
from core.ollama_client import generate
import config


# ═══════════════════════════════════════════════════════════════
#  Existing diagram generators
# ═══════════════════════════════════════════════════════════════

def generate_class_diagram(focus_class: str = None) -> str:
    """
    Generate a PlantUML class diagram.
    If *focus_class* is given, retrieves chunks related to that class;
    otherwise retrieves a broad sample.
    """
    question = (
        f"Generate a DETAILED PlantUML class diagram for the class '{focus_class}'. "
        f"Include ALL its fields with types and visibility (+/-/#), ALL methods "
        f"with return types and parameters, and ALL relationships with other classes "
        f"(inheritance --|>, composition *--, dependency ..>, association -->). "
        f"Add <<stereotype>> annotations (<<Activity>>, <<ViewModel>>, etc.). "
        f"Group related classes inside package blocks. Add notes for design patterns."
        if focus_class
        else "Generate a DETAILED PlantUML class diagram showing the main classes "
             "in this project. For each class include: fields with types and visibility "
             "(+/-/#), methods with return types, <<stereotype>> annotations, and "
             "ALL relationships (inheritance, composition, dependency, association) "
             "with multiplicity labels. Group classes into architectural layer packages. "
             "Add notes for design patterns (Singleton, Observer, Repository, etc.)."
    )
    raw = rag_engine.query(question, analysis_type="class_diagram", top_k=15)
    return _extract_and_validate(raw, "class_diagram")


def generate_sequence_diagram(focus: str = None) -> str:
    """
    Generate a PlantUML sequence diagram.
    """
    question = (
        f"Generate a DETAILED PlantUML sequence diagram showing how '{focus}' "
        f"interacts with other classes. Declare participants with <<stereotypes>>. "
        f"Use activate/deactivate for lifeline bars. Show method call arguments "
        f"and return values. Use alt/opt/loop fragments for control flow. "
        f"Add notes for important logic steps."
        if focus
        else "Generate a DETAILED PlantUML sequence diagram showing a complete "
             "user interaction flow from UI through business logic to data layer. "
             "Declare participants with <<stereotypes>> (<<Activity>>, <<ViewModel>>, "
             "<<Repository>>). Use activate/deactivate lifeline bars. Show method "
             "arguments and return values. Include alt/opt/loop fragments for "
             "conditional logic. Add notes explaining key decisions."
    )
    raw = rag_engine.query(question, analysis_type="sequence_diagram", top_k=15)
    return _extract_and_validate(raw, "sequence_diagram")


def generate_activity_diagram() -> str:
    """
    Generate a PlantUML activity diagram showing navigation flows.
    """
    question = (
        "Generate a DETAILED PlantUML activity diagram showing all screen "
        "navigation flows in this Android app. Use |Swimlane| syntax to "
        "separate UI, business logic, and data layer responsibilities. "
        "Use if/then/else diamonds for user decisions and conditional branches. "
        "Use fork/join for parallel operations. Show complete flows from "
        "app launch to key features. Add notes for important business rules."
    )
    raw = rag_engine.query(
        question, analysis_type="activity_diagram",
        top_k=15, layer_filter="UI",
    )
    return _extract_and_validate(raw, "activity_diagram")


# ═══════════════════════════════════════════════════════════════
#  New diagram generators
# ═══════════════════════════════════════════════════════════════

def generate_state_diagram(focus_class: str = None) -> str:
    """
    Generate a PlantUML state diagram showing lifecycle states
    and transitions for an Android component or business object.
    """
    question = (
        f"Generate a DETAILED PlantUML state diagram for '{focus_class}'. "
        f"Define states with 'state \"Name\" as S1' syntax. Add entry/do/exit "
        f"actions inside each state. Show guard conditions on transitions: "
        f"S1 --> S2 : event [guard]. Use [*] for initial/final states. "
        f"Use composite states for nested lifecycles. Add notes explaining "
        f"lifecycle callbacks (onCreate, onResume, onPause, onDestroy)."
        if focus_class
        else "Generate a DETAILED PlantUML state diagram showing the complete "
             "lifecycle of the main Activity or Fragment. Define states with "
             "'state \"Name\" as S1'. Include entry/do/exit actions. Show ALL "
             "lifecycle transitions with guard conditions. Use [*] for "
             "initial/final states. Use composite states for complex flows. "
             "Add notes explaining Android lifecycle callbacks."
    )
    raw = rag_engine.query(question, analysis_type="state_diagram", top_k=15)
    return _extract_and_validate(raw, "state_diagram")


def generate_component_diagram() -> str:
    """
    Generate a PlantUML component diagram showing Android Manifest
    components and their interactions via Intents.
    """
    question = (
        "Generate a DETAILED PlantUML component diagram showing ALL Android "
        "components: Activities, Services, BroadcastReceivers, ContentProviders, "
        "and Repositories. Declare each with <<stereotype>> annotations. "
        "Group components into package blocks by feature area (e.g. Auth, "
        "Main, Settings). Show interactions with labels: Intent, BoundService, "
        "ContentURI, Repository call. Define interfaces for key contracts."
    )
    raw = rag_engine.query(question, analysis_type="component_diagram", top_k=15)
    return _extract_and_validate(raw, "component_diagram")


def generate_usecase_diagram() -> str:
    """
    Generate a PlantUML use-case diagram showing actor–system interactions
    extracted from the UI and ViewModel layers.
    """
    question = (
        "Generate a DETAILED PlantUML use case diagram for this Android app. "
        "Use 'left to right direction'. Define actors with 'actor \"Name\" as A1'. "
        "Wrap the system in 'rectangle \"AppName\" { }'. Define use cases with "
        "'usecase \"Name\" as UC1'. CRITICAL: in relationships, ALWAYS use "
        "parentheses: 'A1 --> (Login)' NOT 'A1 --> Login'. Show <<include>> "
        "and <<extend>> relationships. Add notes describing key use cases. "
        "Derive use cases from actual Activities, Fragments, and ViewModels."
    )
    raw = rag_engine.query(question, analysis_type="usecase_diagram", top_k=15)
    return _extract_and_validate(raw, "usecase_diagram")


def generate_package_diagram() -> str:
    """
    Generate a PlantUML package diagram showing the package hierarchy
    and inter-layer dependencies (UI → Domain → Data).
    """
    question = (
        "Generate a DETAILED PlantUML package diagram for this project. "
        "Define packages with layer stereotypes and colors: "
        "'package \"ui\" <<Presentation>> #1e293b { class ClassName }'. "
        "List actual class names inside each package. Draw directional "
        "dependency arrows with labels (e.g. 'ui ..> domain : uses'). "
        "Flag any clean architecture violations with 'note on link' warnings. "
        "Use different background colors per layer."
    )
    raw = rag_engine.query(question, analysis_type="package_diagram", top_k=15)
    return _extract_and_validate(raw, "package_diagram")


def generate_deployment_diagram() -> str:
    """
    Generate a PlantUML deployment diagram showing the app's external
    connections: REST APIs, databases, Firebase, third-party SDKs.
    """
    question = (
        "Generate a DETAILED PlantUML deployment diagram for this app. "
        "Use nested 'node \"Android Device\" { node \"App Process\" { } }' "
        "structure. Use proper shapes: 'database' for DB, 'cloud' for services, "
        "'node' for servers, 'artifact' for APK/files. Label ALL connections "
        "with protocol AND library (e.g. 'HTTPS\\n(Retrofit + OkHttp)'). "
        "Include all external services found: REST APIs, Firebase, databases, "
        "analytics SDKs. Add notes describing component purposes."
    )
    raw = rag_engine.query(question, analysis_type="deployment_diagram", top_k=15)
    return _extract_and_validate(raw, "deployment_diagram")


# ═══════════════════════════════════════════════════════════════
#  Skinparam injection — ensures consistent styling on every diagram
# ═══════════════════════════════════════════════════════════════

# Default skinparam block applied to ALL diagrams as a baseline.
# Diagram-specific styles from the LLM prompt will override these.
_DEFAULT_SKINPARAM = """
skinparam defaultFontName "Segoe UI"
skinparam defaultFontSize 12
skinparam shadowing true
skinparam roundCorner 8
skinparam BackgroundColor #0f172a
skinparam ArrowColor #06b6d4
skinparam ArrowFontColor #94a3b8
skinparam ArrowFontSize 11
skinparam noteBorderColor #334155
skinparam noteBackgroundColor #1e293b
skinparam noteFontColor #e2e8f0
skinparam titleFontSize 16
skinparam titleFontColor #e2e8f0
""".strip()


def _inject_skinparam(code: str) -> str:
    """
    Inject default skinparam styling right after @startuml if the LLM
    didn't already include comprehensive skinparam directives.

    This guarantees every diagram gets a consistent, professional look
    even when the LLM ignores the styling instructions in the prompt.
    """
    # Count how many skinparam lines the LLM already included
    existing_skinparams = sum(
        1 for line in code.split("\n")
        if line.strip().lower().startswith("skinparam")
    )

    # If the LLM included 5+ skinparam lines, it likely followed our
    # styling instructions — only inject the font/shadow defaults.
    if existing_skinparams >= 5:
        minimal = (
            'skinparam defaultFontName "Segoe UI"\n'
            'skinparam shadowing true\n'
            'skinparam roundCorner 8'
        )
        return code.replace(
            "@startuml",
            f"@startuml\n{minimal}",
            1,
        )

    # Otherwise inject the full default styling block
    return code.replace(
        "@startuml",
        f"@startuml\n{_DEFAULT_SKINPARAM}",
        1,
    )


# ═══════════════════════════════════════════════════════════════
#  Registry — maps diagram type names to their generators
# ═══════════════════════════════════════════════════════════════

# Each entry: display_name -> (generator_func, needs_focus_class)
DIAGRAM_REGISTRY = {
    "Class Diagram":       (generate_class_diagram,      True),
    "Sequence Diagram":    (generate_sequence_diagram,    True),
    "Activity Diagram":    (generate_activity_diagram,    False),
    "State Machine Diagram": (generate_state_diagram,     True),
    "Component Diagram":   (generate_component_diagram,   False),
    "Use Case Diagram":    (generate_usecase_diagram,     False),
    "Package Diagram":     (generate_package_diagram,     False),
    "Deployment Diagram":  (generate_deployment_diagram,  False),
}


# ═══════════════════════════════════════════════════════════════
#  PlantUML extraction, validation, repair, and retry
# ═══════════════════════════════════════════════════════════════

# Regex to capture @startuml ... @enduml blocks (including across newlines)
_PUML_BLOCK_RE = re.compile(
    r'@startuml.*?@enduml', re.DOTALL | re.IGNORECASE
)

# Code fence extraction pattern (precompiled for performance)
_CODE_FENCE_RE = re.compile(
    r'```(?:plantuml|puml|uml)?\s*\n(.*?)```',
    re.DOTALL | re.IGNORECASE,
)

# Markers that indicate the LLM returned an error instead of a diagram
_ERROR_MARKERS = [
    "[Ollama error",
    "[Streaming error",
    "I cannot generate",
    "I'm sorry",
    "I apologize",
    "As an AI",
]

# ── Precompiled patterns for _repair_plantuml (Item 10) ────────
_RE_COLON_EXTENDS = re.compile(
    r'^(\s*(?:abstract\s+)?class\s+\w+)\s*:\s*(\w+)',
    re.MULTILINE,
)
_RE_EXTENDS_IFACE = re.compile(
    r'^(\s*(?:abstract\s+)?class\s+\w+)\s*extends\s+(I[A-Z]\w*Interface|\w*able)',
    re.MULTILINE,
)
_RE_ARROW_TARGET = re.compile(
    r'(-+->|\.\.+>|<-+-|<\.\.+)\s+(?!["(])([A-Z][a-zA-Z]*(?:\s+[A-Za-z/]+)+)\s*$',
    re.MULTILINE,
)
_RE_ARROW_SOURCE = re.compile(
    r'^\s*(?!["(])([A-Z][a-zA-Z]*(?:\s+[A-Za-z/]+)+)\s+(-+->|\.\.+>)',
    re.MULTILINE,
)
_COMMENTARY_PREFIXES = (
    "here is", "here's", "below is", "this diagram",
    "note:", "explanation:", "the above", "as you can see",
    "i hope", "let me", "please note", "sure,",
)


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
            print(f"[PlantUML Extract] LLM returned error-like text: {text[:100]}...")
            return "@startuml\n' LLM could not generate diagram\n@enduml"

    # 1. Regex: find all @startuml...@enduml blocks
    matches = _PUML_BLOCK_RE.findall(text)
    if matches:
        # Use the longest block (most likely the complete diagram)
        best = max(matches, key=len)
        return best.strip()

    # 2. Code fences: ```plantuml ... ``` or ```puml ... ``` or just ``` ... ```
    fence_matches = _CODE_FENCE_RE.findall(text)
    if fence_matches:
        body = max(fence_matches, key=len).strip()
        # If the body already has @startuml, extract it
        inner = _PUML_BLOCK_RE.findall(body)
        if inner:
            return max(inner, key=len).strip()
        return f"@startuml\n{body}\n@enduml"

    # 3. Fallback: wrap entire output (strip common chat prefixes)
    stripped = text.strip()
    # Remove common LLM prefix phrases
    for prefix in [
        "Here is", "Here's", "Below is", "The following",
        "Sure,", "Sure!", "Certainly",
    ]:
        if stripped.lower().startswith(prefix.lower()):
            # Find the first newline after the prefix
            nl_idx = stripped.find("\n")
            if nl_idx != -1:
                stripped = stripped[nl_idx + 1:].strip()
            break

    return f"@startuml\n{stripped}\n@enduml"


def _validate_plantuml(code: str) -> tuple:
    """
    Basic syntax validation for PlantUML code.

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
        # Only contains comments — effectively empty
        lines = [l.strip() for l in body.split("\n") if l.strip() and not l.strip().startswith("'")]
        if not lines:
            return False, "Diagram body is empty or contains only comments"

    # Check balanced braces/brackets
    open_braces = body.count("{")
    close_braces = body.count("}")
    if open_braces != close_braces:
        return False, f"Unbalanced braces: {open_braces} open vs {close_braces} close"

    return True, ""


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

    # Extract body for repairs
    start = code.index("@startuml")
    end = code.index("@enduml") + len("@enduml")
    header = code[start:start + len("@startuml")]
    footer = code[end - len("@enduml"):end]
    body = code[start + len("@startuml"):end - len("@enduml")]

    # ── Fix Kotlin/C++ style inheritance: "class Foo : Bar" → "class Foo extends Bar" ──
    body = _RE_COLON_EXTENDS.sub(r'\1 extends \2', body)

    # ── Fix Kotlin/C++ style interface impl: "class Foo : IBar" → "class Foo implements IBar" ──
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

    # Fix unbalanced braces — add missing closing braces at the end
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
    print(f"[PlantUML Retry] Asking {target_model} to fix syntax error: {error_msg}")
    raw = generate(repair_prompt, model=target_model)
    return _extract_plantuml(raw)


def _test_render_kroki(code: str) -> tuple:
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
        # Network error — assume it might render, don't block
        return True, ""


def _extract_and_validate(raw_llm_output: str,
                          analysis_type: str = "general") -> str:
    """
    Full pipeline: extract → repair → validate → test-render → retry.
    """
    # Step 1: Extract
    code = _extract_plantuml(raw_llm_output)

    # Step 2: Always run repair (it's idempotent on valid code)
    code = _repair_plantuml(code)

    # Step 3: Local validation
    is_valid, error = _validate_plantuml(code)
    if not is_valid:
        print(f"[PlantUML Validate] Local validation failed: {error}")
        # Try LLM retry for structural issues
        try:
            retried = _retry_with_llm(code, error, analysis_type)
            retried = _repair_plantuml(retried)
            is_valid, _ = _validate_plantuml(retried)
            if is_valid:
                print("[PlantUML Validate] LLM retry fixed local validation")
                code = retried
            else:
                print("[PlantUML Validate] LLM retry still has local issues, using best effort")
        except Exception as e:
            print(f"[PlantUML Validate] LLM retry error: {e}")

    # Step 4: Test-render via Kroki (catches syntax issues local validation misses)
    renderable, render_error = _test_render_kroki(code)
    if renderable:
        return _inject_skinparam(code)

    print(f"[PlantUML Validate] Kroki test-render failed: {render_error}")

    # Step 5: LLM retry with Kroki error (only once)
    try:
        retried = _retry_with_llm(code, render_error, analysis_type)
        retried = _repair_plantuml(retried)
        renderable, _ = _test_render_kroki(retried)
        if renderable:
            print("[PlantUML Validate] LLM retry fixed Kroki rendering")
            return _inject_skinparam(retried)
        print("[PlantUML Validate] LLM retry still fails Kroki, returning best effort")
        return _inject_skinparam(retried)
    except Exception as e:
        print(f"[PlantUML Validate] LLM retry error: {e}")
        return _inject_skinparam(code)
