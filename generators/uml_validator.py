"""
UML IR validator.

Validation happens before deterministic PlantUML compilation. The checks here
focus on two things:
1. Structural correctness: declared references, duplicates, required fields.
2. UML semantic correctness: the selected diagram should actually model the
   right concept instead of drifting into another UML view.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from generators.uml_ir import (
    ActivityDiagramIR,
    ClassDiagramIR,
    ComponentDiagramIR,
    DeploymentDiagramIR,
    NavigationDiagramIR,
    PackageDiagramIR,
    SequenceDiagramIR,
    StateDiagramIR,
    UseCaseDiagramIR,
)

ValidationResult = Tuple[bool, List[str]]


def _check_non_empty(value: str, field_name: str, errors: List[str]):
    if not value or not value.strip():
        errors.append(f"{field_name} is empty or missing")


def _check_duplicates(items, key_fn, entity_type: str, errors: List[str]):
    seen = set()
    for item in items:
        key = key_fn(item)
        if not key:
            continue
        lowered = key.strip().lower()
        if lowered in seen:
            errors.append(f"Duplicate {entity_type}: {key!r}")
        seen.add(lowered)


def _check_note_targets(notes, declared: set, label: str, errors: List[str], allow_empty: bool = False):
    for note in notes:
        if not note.target:
            if allow_empty:
                continue
            errors.append(f"{label} note target is empty")
            continue
        if note.target not in declared:
            errors.append(f"{label} note target {note.target!r} is not declared")


def _looks_like_ui_or_code_name(name: str) -> bool:
    compact = (name or "").replace(" ", "")
    if not compact:
        return False
    suffixes = (
        "Activity",
        "Fragment",
        "ViewModel",
        "Repository",
        "Controller",
        "Presenter",
        "Screen",
        "Page",
        "Service",
        "Adapter",
    )
    if any(compact.endswith(suffix) for suffix in suffixes):
        return True
    return any(token in compact for token in (".", "/", "(", ")", "{", "}", "_"))


def _usecase_relation_kind(label: str, arrow_type: str) -> str:
    text = f"{label} {arrow_type}".lower()
    if "include" in text:
        return "include"
    if "extend" in text:
        return "extend"
    if "general" in text or "|>" in arrow_type:
        return "generalization"
    return "association"


def validate_class_diagram(ir: ClassDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.classes:
        return False, ["No classes defined"]

    if len(ir.classes) > 15:
        errors.append(f"Too many classes ({len(ir.classes)}), limit is 15")

    declared = set()
    for cls in ir.classes:
        _check_non_empty(cls.name, "class.name", errors)
        declared.add(cls.name)
    for cls in ir.external_classes:
        if cls.name:
            declared.add(cls.name)

    _check_duplicates(ir.classes, lambda item: item.name, "class", errors)

    for rel in ir.relationships:
        _check_non_empty(rel.source, "relationship.source", errors)
        _check_non_empty(rel.target, "relationship.target", errors)
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source {rel.source!r} is not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target {rel.target!r} is not declared")

    _check_note_targets(ir.notes, declared, "Class diagram", errors)
    return (len(errors) == 0, errors)


def validate_usecase_diagram(ir: UseCaseDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.system_name.strip():
        errors.append("system_name is empty")
    if not ir.actors:
        errors.append("No actors defined")
    if not ir.usecases:
        errors.append("No use cases defined")
        return False, errors

    if len(ir.usecases) > 20:
        errors.append(f"Too many use cases ({len(ir.usecases)}), limit is 20")

    actor_names = {actor.name for actor in ir.actors if actor.name}
    actor_refs = set(actor_names)
    usecase_names = {usecase.name for usecase in ir.usecases if usecase.name}
    usecase_refs = set(usecase_names)

    _check_duplicates(ir.actors, lambda item: item.name, "actor", errors)
    _check_duplicates(ir.usecases, lambda item: item.name, "use case", errors)

    for actor in ir.actors:
        _check_non_empty(actor.name, "actor.name", errors)
        if actor.alias:
            actor_refs.add(actor.alias)
    for usecase in ir.usecases:
        _check_non_empty(usecase.name, "usecase.name", errors)
        if _looks_like_ui_or_code_name(usecase.name):
            errors.append(
                f"Use case {usecase.name!r} looks like a screen or code identifier instead of a user goal"
            )
        if usecase.alias:
            usecase_refs.add(usecase.alias)

    declared = actor_refs | usecase_refs

    def _kind(endpoint: str) -> str:
        if endpoint in actor_refs:
            return "actor"
        if endpoint in usecase_refs:
            return "usecase"
        return ""

    for rel in ir.relationships:
        _check_non_empty(rel.source, "relationship.source", errors)
        _check_non_empty(rel.target, "relationship.target", errors)
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source {rel.source!r} is not declared")
            continue
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target {rel.target!r} is not declared")
            continue

        src_kind = _kind(rel.source)
        tgt_kind = _kind(rel.target)
        rel_kind = _usecase_relation_kind(rel.label, rel.arrow_type)

        if src_kind == "actor" and tgt_kind == "usecase":
            if rel_kind not in ("association", "generalization"):
                errors.append(
                    f"Actor-to-usecase relationship {rel.source!r}->{rel.target!r} cannot be {rel_kind}"
                )
        elif src_kind == "usecase" and tgt_kind == "actor":
            if rel_kind != "association":
                errors.append(
                    f"Usecase-to-actor relationship {rel.source!r}->{rel.target!r} must be a plain association"
                )
        elif src_kind == "usecase" and tgt_kind == "usecase":
            if rel_kind not in ("include", "extend", "generalization"):
                errors.append(
                    f"Usecase relationship {rel.source!r}->{rel.target!r} has unsupported type {rel_kind}"
                )
        elif src_kind == "actor" and tgt_kind == "actor":
            if rel_kind != "generalization":
                errors.append(
                    f"Actor relationship {rel.source!r}->{rel.target!r} should only be generalization"
                )
        else:
            errors.append(
                f"Relationship {rel.source!r}->{rel.target!r} mixes undeclared or invalid endpoint types"
            )

        if rel_kind in ("include", "extend") and not (src_kind == "usecase" and tgt_kind == "usecase"):
            errors.append(
                f"{rel_kind} relationship {rel.source!r}->{rel.target!r} must connect use case to use case"
            )

    _check_note_targets(ir.notes, actor_names | usecase_names, "Use case diagram", errors)
    return (len(errors) == 0, errors)


def validate_sequence_diagram(ir: SequenceDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.participants:
        return False, ["No participants defined"]
    if len(ir.participants) > 10:
        errors.append(f"Too many participants ({len(ir.participants)}), limit is 10")

    declared = set()
    names_only = set()
    for participant in ir.participants:
        _check_non_empty(participant.name, "participant.name", errors)
        declared.add(participant.name)
        names_only.add(participant.name)
        if participant.alias:
            declared.add(participant.alias)

    _check_duplicates(ir.participants, lambda item: item.name, "participant", errors)

    def _check_messages(messages, context: str):
        for message in messages:
            _check_non_empty(message.sender, f"{context}.sender", errors)
            _check_non_empty(message.receiver, f"{context}.receiver", errors)
            _check_non_empty(message.label, f"{context}.label", errors)
            if message.sender and message.sender not in declared:
                errors.append(f"Message sender {message.sender!r} is not declared")
            if message.receiver and message.receiver not in declared:
                errors.append(f"Message receiver {message.receiver!r} is not declared")

    _check_messages(ir.messages, "message")

    for group in ir.groups:
        if group.group_type in ("opt", "loop") and group.else_messages:
            errors.append(f"{group.group_type} group cannot contain else_messages")
        _check_messages(group.messages, f"{group.group_type}.message")
        _check_messages(group.else_messages, f"{group.group_type}.else_message")

    if not ir.messages and not ir.groups:
        errors.append("No messages or groups defined")

    _check_note_targets(ir.notes, names_only, "Sequence diagram", errors)
    return (len(errors) == 0, errors)


def validate_activity_diagram(ir: ActivityDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.steps:
        return False, ["No steps defined"]

    swimlanes = {lane for lane in ir.swimlanes if lane}
    _check_duplicates(ir.swimlanes, lambda item: str(item), "swimlane", errors)

    action_count = 0

    def _check_steps(steps, depth: int = 0):
        nonlocal action_count
        if depth > 5:
            errors.append("Decision nesting too deep (>5)")
            return
        for step in steps:
            if step.swimlane and swimlanes and step.swimlane not in swimlanes:
                errors.append(f"Step swimlane {step.swimlane!r} is not declared")
            if step.step_type == "action":
                action_count += 1
                _check_non_empty(step.label, "step.label", errors)
            elif step.step_type == "decision":
                _check_non_empty(step.condition, "decision.condition", errors)
                if not step.yes_steps:
                    errors.append("Decision has no yes_steps")
                _check_steps(step.yes_steps, depth + 1)
                _check_steps(step.no_steps, depth + 1)
            elif step.step_type == "fork":
                _check_non_empty(step.label, "fork.label", errors)

    _check_steps(ir.steps)

    if action_count == 0:
        errors.append("Activity diagram has no action steps")

    return (len(errors) == 0, errors)


def validate_state_diagram(ir: StateDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.states:
        return False, ["No states defined"]

    declared = set()
    for state in ir.states:
        _check_non_empty(state.name, "state.name", errors)
        declared.add(state.name)

    _check_duplicates(ir.states, lambda item: item.name, "state", errors)

    if not ir.transitions:
        errors.append("No transitions defined")

    initial_count = 0
    for transition in ir.transitions:
        if transition.source == "[*]":
            initial_count += 1
        if transition.source == "[*]" and transition.target == "[*]":
            errors.append("Transition cannot go directly from [*] to [*]")
        if transition.source != "[*]" and transition.source not in declared:
            errors.append(f"Transition source {transition.source!r} is not declared")
        if transition.target != "[*]" and transition.target not in declared:
            errors.append(f"Transition target {transition.target!r} is not declared")
    if initial_count == 0:
        errors.append("State diagram must have an initial transition from [*]")

    _check_note_targets(ir.notes, declared, "State diagram", errors)
    return (len(errors) == 0, errors)


def validate_component_diagram(ir: ComponentDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.components:
        return False, ["No components defined"]

    declared = set()
    names_only = set()

    for component in ir.components:
        _check_non_empty(component.name, "component.name", errors)
        declared.add(component.name)
        names_only.add(component.name)
    for iface in ir.interfaces:
        _check_non_empty(iface.name, "interface.name", errors)
        declared.add(iface.name)
        names_only.add(iface.name)
        if iface.alias:
            declared.add(iface.alias)
    for component in ir.external_components:
        if component.name:
            declared.add(component.name)
            names_only.add(component.name)

    _check_duplicates(ir.components, lambda item: item.name, "component", errors)

    for rel in ir.relationships:
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source {rel.source!r} is not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target {rel.target!r} is not declared")

    _check_note_targets(ir.notes, names_only, "Component diagram", errors)
    return (len(errors) == 0, errors)


def validate_package_diagram(ir: PackageDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.packages:
        return False, ["No packages defined"]

    package_names = set()
    class_names = set()
    for package in ir.packages:
        _check_non_empty(package.name, "package.name", errors)
        if not package.classes:
            errors.append(f"Package {package.name!r} has no classes")
        lowered = package.name.strip().lower()
        if lowered in package_names:
            errors.append(f"Duplicate package: {package.name!r}")
        package_names.add(lowered)
        for class_name in package.classes:
            if not str(class_name).strip():
                errors.append(f"Package {package.name!r} contains an empty class name")
                continue
            class_key = str(class_name).strip().lower()
            if class_key in class_names:
                errors.append(f"Representative class {class_name!r} appears in multiple packages")
            class_names.add(class_key)

    declared = {package.name for package in ir.packages}
    for package in ir.packages:
        declared.update(package.classes)

    for rel in ir.relationships:
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source {rel.source!r} is not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target {rel.target!r} is not declared")

    _check_note_targets(ir.notes, declared, "Package diagram", errors, allow_empty=True)
    return (len(errors) == 0, errors)


def validate_deployment_diagram(ir: DeploymentDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.nodes:
        return False, ["No nodes defined"]

    declared = set()
    for node in ir.nodes:
        _check_non_empty(node.name, "node.name", errors)
        if node.name:
            if node.name in declared:
                errors.append(f"Duplicate node or child name: {node.name!r}")
            declared.add(node.name)
        for child in node.children:
            _check_non_empty(child.name, "node.child.name", errors)
            if child.name:
                if child.name in declared:
                    errors.append(f"Duplicate node or child name: {child.name!r}")
                declared.add(child.name)

    for rel in ir.relationships:
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source {rel.source!r} is not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target {rel.target!r} is not declared")

    _check_note_targets(ir.notes, declared, "Deployment diagram", errors)
    return (len(errors) == 0, errors)


def validate_navigation_diagram(ir: NavigationDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.screens:
        return False, ["No screens defined"]

    screen_names = set()
    declared = set()
    for screen in ir.screens:
        _check_non_empty(screen.name, "screen.name", errors)
        if screen.name:
            lowered = screen.name.lower()
            if lowered in screen_names:
                errors.append(f"Duplicate screen: {screen.name!r}")
            screen_names.add(lowered)
            declared.add(screen.name)
        if screen.display_name:
            declared.add(screen.display_name)

    if ir.entry_screen and ir.entry_screen not in declared:
        errors.append(f"entry_screen {ir.entry_screen!r} is not declared")

    if not ir.transitions:
        errors.append("No navigation transitions defined")

    for transition in ir.transitions:
        if transition.source != "[*]" and transition.source not in declared:
            errors.append(f"Transition source {transition.source!r} is not declared")
        if transition.target != "[*]" and transition.target not in declared:
            errors.append(f"Transition target {transition.target!r} is not declared")
        _check_non_empty(transition.label, "transition.label", errors)

    for exit_screen in ir.exit_screens:
        if exit_screen not in declared:
            errors.append(f"Exit screen {exit_screen!r} is not declared")

    _check_note_targets(ir.notes, declared, "Navigation diagram", errors)
    return (len(errors) == 0, errors)


IR_VALIDATORS = {
    "class_diagram": validate_class_diagram,
    "usecase_diagram": validate_usecase_diagram,
    "sequence_diagram": validate_sequence_diagram,
    "activity_diagram": validate_activity_diagram,
    "state_diagram": validate_state_diagram,
    "component_diagram": validate_component_diagram,
    "package_diagram": validate_package_diagram,
    "deployment_diagram": validate_deployment_diagram,
    "navigation_diagram": validate_navigation_diagram,
}


def validate_ir(diagram_type: str, ir) -> ValidationResult:
    validator = IR_VALIDATORS.get(diagram_type)
    if validator is None:
        return False, [f"No validator for diagram type: {diagram_type}"]
    return validator(ir)


_LEAK_PATTERNS = [
    re.compile(r"<thinking>", re.IGNORECASE),
    re.compile(r"</thinking>", re.IGNORECASE),
    re.compile(r"```", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"<\|EOT\|>", re.IGNORECASE),
    re.compile(r"\bhere is\b", re.IGNORECASE),
    re.compile(r"\bhere's\b", re.IGNORECASE),
    re.compile(r"\bbelow is\b", re.IGNORECASE),
    re.compile(r"\bi hope\b", re.IGNORECASE),
    re.compile(r"\blet me\b", re.IGNORECASE),
    re.compile(r"\bcertainly\b", re.IGNORECASE),
    re.compile(r"\bsure,\b", re.IGNORECASE),
]

_ERROR_TEXT_PATTERNS = [
    re.compile(r"\bollama error\b", re.IGNORECASE),
    re.compile(r"\btraceback\b", re.IGNORECASE),
    re.compile(r"\bexception\b", re.IGNORECASE),
    re.compile(r"\bsyntax error\b", re.IGNORECASE),
    re.compile(r"\bgeneration failed\b", re.IGNORECASE),
]

_EMPTY_TARGETED_NOTE_RE = re.compile(
    r"\bnote\s+(right|left|top|bottom)\s+of\s*(?::|$)",
    re.IGNORECASE | re.MULTILINE,
)


def validate_compiled_plantuml(code: str, diagram_type: str = "") -> ValidationResult:
    """Validate compiled PlantUML output."""
    errors: List[str] = []

    if not code or not code.strip():
        return False, ["Empty PlantUML code"]

    if "@startuml" not in code:
        errors.append("Missing @startuml tag")
    if "@enduml" not in code:
        errors.append("Missing @enduml tag")
    if code.count("@startuml") > 1:
        errors.append("Duplicate @startuml tag")
    if code.count("@enduml") > 1:
        errors.append("Duplicate @enduml tag")

    if errors:
        return False, errors

    start = code.index("@startuml") + len("@startuml")
    end = code.index("@enduml")
    body = code[start:end].strip()

    if not body:
        return False, ["Diagram body is empty"]

    open_braces = body.count("{")
    close_braces = body.count("}")
    if open_braces != close_braces:
        errors.append(f"Unbalanced braces: {open_braces} open vs {close_braces} close")

    if _EMPTY_TARGETED_NOTE_RE.search(body):
        errors.append("Found note with missing target")

    for pattern in _LEAK_PATTERNS:
        if pattern.search(body):
            errors.append(f"Leaked LLM text detected: {pattern.pattern}")

    for pattern in _ERROR_TEXT_PATTERNS:
        if pattern.search(body):
            errors.append(f"Found error text in diagram body: {pattern.pattern}")

    if diagram_type == "sequence_diagram":
        activates = len(re.findall(r"\bactivate\b", body))
        deactivates = len(re.findall(r"\bdeactivate\b", body))
        if activates != deactivates:
            errors.append(f"Unbalanced activate/deactivate: {activates} vs {deactivates}")
        opens = len(re.findall(r"\b(alt|opt|loop|group|critical)\b", body))
        ends = len(re.findall(r"\bend\b", body))
        if opens != ends:
            errors.append(f"Unbalanced control blocks: {opens} opens vs {ends} ends")

    if diagram_type == "activity_diagram":
        ifs = len(re.findall(r"\bif\s*\(", body))
        endifs = len(re.findall(r"\bendif\b", body))
        if ifs != endifs:
            errors.append(f"Unbalanced if/endif: {ifs} vs {endifs}")

    non_comment_lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip()
        and not line.strip().startswith("'")
        and not line.strip().startswith("skinparam")
        and not line.strip().startswith("title")
    ]
    if len(non_comment_lines) < 2:
        errors.append("Diagram has too few meaningful lines")

    return (len(errors) == 0, errors)
