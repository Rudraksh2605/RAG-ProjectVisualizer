"""
UML IR Validator — validates structured IR before compilation.

Catches errors that would cause PlantUML rendering failures:
  - Missing required fields
  - Empty names
  - Dangling relationship references
  - Duplicate entities
  - Out-of-range counts
  - Invalid enum/type values

Also provides post-compile PlantUML validation that is stronger than
the original heuristic validator.
"""

from __future__ import annotations
import re
import logging
from typing import List, Tuple

from generators.uml_ir import (
    ClassDiagramIR, UseCaseDiagramIR, SequenceDiagramIR,
    ActivityDiagramIR, StateDiagramIR, ComponentDiagramIR,
    PackageDiagramIR, DeploymentDiagramIR, NavigationDiagramIR,
    ActivityStepIR,
)

log = logging.getLogger("uml_validator")

# Return type: (is_valid, list_of_error_strings)
ValidationResult = Tuple[bool, List[str]]


# ═══════════════════════════════════════════════════════════════
#  Generic helpers
# ═══════════════════════════════════════════════════════════════

def _check_non_empty(value: str, field_name: str, errors: List[str]):
    if not value or not value.strip():
        errors.append(f"'{field_name}' is empty or missing")


def _check_no_duplicates(items: list, key_fn, entity_type: str, errors: List[str]):
    seen = set()
    for item in items:
        k = key_fn(item)
        if k in seen:
            errors.append(f"Duplicate {entity_type}: '{k}'")
        seen.add(k)


# ═══════════════════════════════════════════════════════════════
#  Per-diagram-type IR validators
# ═══════════════════════════════════════════════════════════════

def validate_class_diagram(ir: ClassDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.classes:
        errors.append("No classes defined")
        return False, errors

    if len(ir.classes) > 15:
        errors.append(f"Too many classes ({len(ir.classes)}), limit to 15")

    declared = set()
    for cls in ir.classes:
        _check_non_empty(cls.name, "class.name", errors)
        if cls.name in declared:
            errors.append(f"Duplicate class: '{cls.name}'")
        declared.add(cls.name)

    for rel in ir.relationships:
        _check_non_empty(rel.source, "relationship.source", errors)
        _check_non_empty(rel.target, "relationship.target", errors)
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source '{rel.source}' not in declared classes")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target '{rel.target}' not in declared classes")

    return (len(errors) == 0, errors)


def validate_usecase_diagram(ir: UseCaseDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.actors:
        errors.append("No actors defined")
    if not ir.usecases:
        errors.append("No use cases defined")
        return False, errors

    if len(ir.usecases) > 20:
        errors.append(f"Too many use cases ({len(ir.usecases)}), limit to 20")

    declared = set()  # accepts both names AND aliases
    for actor in ir.actors:
        _check_non_empty(actor.name, "actor.name", errors)
        declared.add(actor.name)
        if actor.alias:
            declared.add(actor.alias)
    for uc in ir.usecases:
        _check_non_empty(uc.name, "usecase.name", errors)
        declared.add(uc.name)
        if uc.alias:
            declared.add(uc.alias)

    _check_no_duplicates(ir.usecases, lambda u: u.name, "use case", errors)

    for rel in ir.relationships:
        _check_non_empty(rel.source, "relationship.source", errors)
        _check_non_empty(rel.target, "relationship.target", errors)
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source '{rel.source}' not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target '{rel.target}' not declared")

    return (len(errors) == 0, errors)


def validate_sequence_diagram(ir: SequenceDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.participants:
        errors.append("No participants defined")
        return False, errors

    if len(ir.participants) > 10:
        errors.append(f"Too many participants ({len(ir.participants)}), limit to 10")

    # Accept both names AND aliases — LLMs frequently use aliases in messages
    declared = set()
    for p in ir.participants:
        _check_non_empty(p.name, "participant.name", errors)
        declared.add(p.name)
        if p.alias:
            declared.add(p.alias)

    _check_no_duplicates(ir.participants, lambda p: p.name, "participant", errors)

    def _check_messages(msgs: list):
        for msg in msgs:
            if msg.sender and msg.sender not in declared:
                errors.append(f"Message sender '{msg.sender}' not declared")
            if msg.receiver and msg.receiver not in declared:
                errors.append(f"Message receiver '{msg.receiver}' not declared")

    _check_messages(ir.messages)
    for grp in ir.groups:
        _check_messages(grp.messages)
        _check_messages(grp.else_messages)

    if not ir.messages and not ir.groups:
        errors.append("No messages or groups defined")

    return (len(errors) == 0, errors)


def validate_activity_diagram(ir: ActivityDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.steps:
        errors.append("No steps defined")
        return False, errors

    def _check_steps(steps: list, depth=0):
        if depth > 5:
            errors.append("Decision nesting too deep (>5)")
            return
        for step in steps:
            if step.step_type == "action":
                _check_non_empty(step.label, "step.label", errors)
            elif step.step_type == "decision":
                _check_non_empty(step.condition, "decision.condition", errors)
                if not step.yes_steps:
                    errors.append("Decision has no 'yes' branch steps")
                _check_steps(step.yes_steps, depth + 1)
                _check_steps(step.no_steps, depth + 1)

    _check_steps(ir.steps)
    return (len(errors) == 0, errors)


def validate_state_diagram(ir: StateDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.states:
        errors.append("No states defined")
        return False, errors

    if len(ir.states) > 12:
        errors.append(f"Too many states ({len(ir.states)}), limit to 12")

    declared = set()
    for s in ir.states:
        _check_non_empty(s.name, "state.name", errors)
        if s.name in declared:
            errors.append(f"Duplicate state: '{s.name}'")
        declared.add(s.name)

    for tr in ir.transitions:
        if tr.source != "[*]" and tr.source not in declared:
            errors.append(f"Transition source '{tr.source}' not declared")
        if tr.target != "[*]" and tr.target not in declared:
            errors.append(f"Transition target '{tr.target}' not declared")

    return (len(errors) == 0, errors)


def validate_component_diagram(ir: ComponentDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.components:
        errors.append("No components defined")
        return False, errors

    # Accept both names AND aliases
    declared = set()
    for c in ir.components:
        _check_non_empty(c.name, "component.name", errors)
        declared.add(c.name)
    for iface in ir.interfaces:
        _check_non_empty(iface.name, "interface.name", errors)
        declared.add(iface.name)
        if iface.alias:
            declared.add(iface.alias)

    _check_no_duplicates(ir.components, lambda c: c.name, "component", errors)

    for rel in ir.relationships:
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source '{rel.source}' not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target '{rel.target}' not declared")

    return (len(errors) == 0, errors)


def validate_package_diagram(ir: PackageDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.packages:
        errors.append("No packages defined")
        return False, errors

    for pkg in ir.packages:
        _check_non_empty(pkg.name, "package.name", errors)
        if not pkg.classes:
            errors.append(f"Package '{pkg.name}' has no classes")

    return (len(errors) == 0, errors)


def validate_deployment_diagram(ir: DeploymentDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.nodes:
        errors.append("No nodes defined")
        return False, errors

    # Include both node names AND their children in the declared set
    declared = set()
    for n in ir.nodes:
        _check_non_empty(n.name, "node.name", errors)
        declared.add(n.name)
        for child in n.children:
            declared.add(child)

    for rel in ir.relationships:
        if rel.source and rel.source not in declared:
            errors.append(f"Relationship source '{rel.source}' not declared")
        if rel.target and rel.target not in declared:
            errors.append(f"Relationship target '{rel.target}' not declared")

    return (len(errors) == 0, errors)


def validate_navigation_diagram(ir: NavigationDiagramIR) -> ValidationResult:
    errors: List[str] = []

    if not ir.screens:
        errors.append("No screens defined")
        return False, errors

    # Accept both name AND display_name
    declared = set()
    for s in ir.screens:
        _check_non_empty(s.name, "screen.name", errors)
        if s.name in declared:
            errors.append(f"Duplicate screen: '{s.name}'")
        declared.add(s.name)
        if s.display_name:
            declared.add(s.display_name)

    for tr in ir.transitions:
        if tr.source != "[*]" and tr.source not in declared:
            errors.append(f"Transition source '{tr.source}' not declared")
        if tr.target != "[*]" and tr.target not in declared:
            errors.append(f"Transition target '{tr.target}' not declared")

    return (len(errors) == 0, errors)


# ═══════════════════════════════════════════════════════════════
#  Validator registry
# ═══════════════════════════════════════════════════════════════

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
    """Validate any IR instance using the appropriate validator."""
    validator = IR_VALIDATORS.get(diagram_type)
    if validator is None:
        return False, [f"No validator for diagram type: {diagram_type}"]
    return validator(ir)


# ═══════════════════════════════════════════════════════════════
#  Post-compile PlantUML validation (stronger than original)
# ═══════════════════════════════════════════════════════════════

# Patterns that indicate leaked LLM text/reasoning
_LEAK_PATTERNS = [
    re.compile(r'<thinking>', re.IGNORECASE),
    re.compile(r'</thinking>', re.IGNORECASE),
    re.compile(r'```', re.IGNORECASE),
    re.compile(r'<\|im_start\|>', re.IGNORECASE),
    re.compile(r'<\|im_end\|>', re.IGNORECASE),
    re.compile(r'<\|EOT\|>', re.IGNORECASE),
    re.compile(r'\bhere is\b', re.IGNORECASE),
    re.compile(r"\bhere's\b", re.IGNORECASE),
    re.compile(r'\bbelow is\b', re.IGNORECASE),
    re.compile(r'\bi hope\b', re.IGNORECASE),
    re.compile(r'\blet me\b', re.IGNORECASE),
    re.compile(r'\bcertainly\b', re.IGNORECASE),
    re.compile(r'\bsure,\b', re.IGNORECASE),
]


def validate_compiled_plantuml(code: str, diagram_type: str = "") -> ValidationResult:
    """
    Validate compiled PlantUML code for correctness.

    This is running on compiler output, so it should mostly pass. But this
    catches any edge-case issues the compiler might have missed.
    """
    errors: List[str] = []

    if not code or not code.strip():
        return False, ["Empty PlantUML code"]

    if "@startuml" not in code:
        errors.append("Missing @startuml tag")
    if "@enduml" not in code:
        errors.append("Missing @enduml tag")

    if errors:
        return False, errors

    # Extract body
    start = code.index("@startuml") + len("@startuml")
    end = code.index("@enduml")
    body = code[start:end].strip()

    if not body:
        errors.append("Diagram body is empty")
        return False, errors

    # Check balanced braces
    open_b = body.count("{")
    close_b = body.count("}")
    if open_b != close_b:
        errors.append(f"Unbalanced braces: {open_b} open vs {close_b} close")

    # Check for leaked LLM text
    for pattern in _LEAK_PATTERNS:
        if pattern.search(body):
            errors.append(f"Leaked LLM text detected: {pattern.pattern}")

    # Check balanced activate/deactivate (sequence diagrams)
    if diagram_type == "sequence_diagram":
        activates = len(re.findall(r'\bactivate\b', body))
        deactivates = len(re.findall(r'\bdeactivate\b', body))
        if activates != deactivates:
            errors.append(f"Unbalanced activate/deactivate: {activates} vs {deactivates}")

    # Check balanced alt/opt/loop vs end (sequence diagrams)
    if diagram_type == "sequence_diagram":
        opens = len(re.findall(r'\b(alt|opt|loop|group|critical)\b', body))
        ends = len(re.findall(r'\bend\b', body))
        if opens != ends:
            errors.append(f"Unbalanced control blocks: {opens} opens vs {ends} ends")

    # Check balanced if/endif (activity diagrams)
    if diagram_type == "activity_diagram":
        ifs = len(re.findall(r'\bif\s*\(', body))
        endifs = len(re.findall(r'\bendif\b', body))
        if ifs != endifs:
            errors.append(f"Unbalanced if/endif: {ifs} vs {endifs}")

    # Body should have meaningful content (not just comments)
    non_comment_lines = [
        line.strip() for line in body.split("\n")
        if line.strip() and not line.strip().startswith("'")
        and not line.strip().startswith("skinparam")
        and not line.strip().startswith("title")
    ]
    if len(non_comment_lines) < 2:
        errors.append("Diagram has too few meaningful lines")

    return (len(errors) == 0, errors)
