"""
Deterministic PlantUML compiler.

The LLM produces structured IR, and this compiler owns the syntax-sensitive
PlantUML decisions. That keeps PlantUML generation deterministic and makes it
possible to repair or reject bad IR before rendering.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from generators.uml_ir import (
    ActivityDiagramIR,
    ActivityStepIR,
    ClassDiagramIR,
    ClassIR,
    ComponentDiagramIR,
    ComponentIR,
    DeploymentChildIR,
    DeploymentDiagramIR,
    MessageIR,
    NavigationDiagramIR,
    PackageDiagramIR,
    SequenceDiagramIR,
    StateDiagramIR,
    UseCaseDiagramIR,
)

log = logging.getLogger("uml_compiler")


def _sanitize_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return "Unknown"
    value = re.sub(r'[<>{}()\[\]`~!@#$%^&*=+|\\;]', "", value)
    value = value.strip()
    return value or "Unknown"


def _quote(text: str) -> str:
    safe = (text or "").replace('"', "'").replace("\n", " ").strip()
    return f'"{safe}"'


def _sanitize_label(text: str) -> str:
    return (text or "").replace('"', "'").replace("\n", " ").strip()


def _valid_arrow(arrow: str) -> str:
    allowed = {
        "-->",
        "<--",
        "--|>",
        "<|--",
        "..|>",
        "<|..",
        "*--",
        "--*",
        "o--",
        "--o",
        "..>",
        "<..",
        "..",
        "--",
        "->",
        "<-",
    }
    return arrow if arrow in allowed else "-->"


def _usecase_relationship_kind(label: str, arrow: str) -> str:
    text = f"{label} {arrow}".lower()
    if "include" in text:
        return "include"
    if "extend" in text:
        return "extend"
    if "general" in text or "|>" in arrow:
        return "generalization"
    return "association"


def _normalize_usecase_relationship(
    source_ref: str,
    target_ref: str,
    label: str,
    arrow: str,
    actor_refs: Set[str],
    usecase_refs: Set[str],
) -> Optional[Tuple[str, str]]:
    src_kind = "actor" if source_ref in actor_refs else "usecase" if source_ref in usecase_refs else ""
    tgt_kind = "actor" if target_ref in actor_refs else "usecase" if target_ref in usecase_refs else ""
    rel_kind = _usecase_relationship_kind(label, arrow)

    if not src_kind or not tgt_kind:
        return None

    if src_kind == "actor" and tgt_kind == "actor":
        if rel_kind != "generalization":
            return None
        return "--|>", ""

    if "actor" in (src_kind, tgt_kind):
        if rel_kind not in ("association", "generalization"):
            if src_kind == "actor" and tgt_kind == "usecase":
                rel_kind = "association"
            else:
                return None
        if rel_kind == "generalization":
            return "--|>", ""
        return "-->", ""

    if rel_kind == "include":
        return "..>", "<<include>>"
    if rel_kind == "extend":
        return "..>", "<<extend>>"
    if rel_kind == "generalization":
        return "--|>", ""
    return "-->", _sanitize_label(label) if label else ""


def compile_class_diagram(ir: ClassDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    packages: Dict[str, List[ClassIR]] = {}
    unpackaged: List[ClassIR] = []
    for cls in ir.classes:
        if cls.package.strip():
            packages.setdefault(cls.package.strip(), []).append(cls)
        else:
            unpackaged.append(cls)

    alias_map: Dict[str, str] = {}
    declared: Set[str] = set()

    def _emit_class(cls: ClassIR) -> List[str]:
        class_name = _sanitize_name(cls.name)
        if class_name in declared:
            return []
        declared.add(class_name)
        alias_map[cls.name] = class_name

        if cls.is_interface:
            keyword = "interface"
        elif cls.is_abstract:
            keyword = "abstract class"
        else:
            keyword = "class"

        stereotype = f" <<{_sanitize_name(cls.stereotype)}>>" if cls.stereotype else ""
        output = [f"{keyword} {_quote(class_name)}{stereotype} {{"]

        for field in cls.fields[:5]:
            field_name = _sanitize_name(field.name)
            field_type = f" : {_sanitize_name(field.type)}" if field.type else ""
            output.append(f"  {field.visibility}{field_name}{field_type}")

        for method in cls.methods[:6]:
            method_name = _sanitize_name(method.name)
            params = f"({_sanitize_label(method.params)})" if method.params else "()"
            return_type = f" : {_sanitize_name(method.return_type)}" if method.return_type else ""
            output.append(f"  {method.visibility}{method_name}{params}{return_type}")

        output.append("}")
        return output

    for package_name, classes in packages.items():
        lines.append(f"package {_quote(package_name)} {{")
        for cls in classes:
            for line in _emit_class(cls):
                lines.append(f"  {line}")
        lines.append("}")
        lines.append("")

    for cls in unpackaged:
        lines.extend(_emit_class(cls))
        lines.append("")

    if ir.external_classes:
        lines.append("' External collaborators")
        for ext in ir.external_classes:
            ext_name = _sanitize_name(ext.name)
            if ext_name in declared:
                continue
            declared.add(ext_name)
            alias_map[ext.name] = ext_name
            stereotype = _sanitize_name(ext.stereotype or "External")
            lines.append(f"class {_quote(ext_name)} <<{stereotype}>>")
        lines.append("")

    for rel in ir.relationships:
        src = alias_map.get(rel.source, _sanitize_name(rel.source))
        tgt = alias_map.get(rel.target, _sanitize_name(rel.target))
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        lines.append(f"{_quote(src)} {_valid_arrow(rel.arrow_type)} {_quote(tgt)}{label}")

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target, _sanitize_name(note.target))
        lines.append(f"note {note.position} of {_quote(target)} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_usecase_diagram(ir: UseCaseDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("left to right direction")
    lines.append("")

    alias_map: Dict[str, str] = {}
    declared_aliases: Set[str] = set()
    actor_refs: Set[str] = set()
    usecase_refs: Set[str] = set()

    for index, actor in enumerate(ir.actors, 1):
        actor_name = _sanitize_name(actor.name)
        alias = re.sub(r"\W+", "", actor.alias.strip() or f"A{index}")
        if alias in declared_aliases:
            alias = f"A{index}_{actor_name[:3]}"
        declared_aliases.add(alias)
        alias_map[actor.name] = alias
        actor_refs.add(actor.name)
        if actor.alias and actor.alias != actor.name:
            alias_map[actor.alias] = alias
            actor_refs.add(actor.alias)
        lines.append(f"actor {_quote(actor_name)} as {alias}")

    lines.append("")

    system_name = _sanitize_name(ir.system_name) if ir.system_name else "System"
    lines.append(f"rectangle {_quote(system_name)} {{")
    for index, usecase in enumerate(ir.usecases, 1):
        usecase_name = _sanitize_name(usecase.name)
        alias = re.sub(r"\W+", "", usecase.alias.strip() or f"UC{index}")
        if alias in declared_aliases:
            alias = f"UC{index}_{usecase_name[:3]}"
        declared_aliases.add(alias)
        alias_map[usecase.name] = alias
        usecase_refs.add(usecase.name)
        if usecase.alias and usecase.alias != usecase.name:
            alias_map[usecase.alias] = alias
            usecase_refs.add(usecase.alias)
        lines.append(f"  usecase {_quote(usecase_name)} as {alias}")
    lines.append("}")
    lines.append("")

    for rel in ir.relationships:
        src = alias_map.get(rel.source, rel.source)
        tgt = alias_map.get(rel.target, rel.target)
        if src not in declared_aliases or tgt not in declared_aliases:
            log.warning("Use case relationship references undeclared endpoint, skipping: %r -> %r", rel.source, rel.target)
            continue
        normalized = _normalize_usecase_relationship(
            rel.source,
            rel.target,
            rel.label,
            rel.arrow_type,
            actor_refs,
            usecase_refs,
        )
        if not normalized:
            log.warning("Use case relationship is semantically invalid, skipping: %r -> %r", rel.source, rel.target)
            continue
        arrow, label_text = normalized
        label = f" : {label_text}" if label_text else ""
        lines.append(f"{src} {arrow} {tgt}{label}")

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target)
        if not target:
            log.warning("Use case note target not declared, skipping: %r", note.target)
            continue
        lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_sequence_diagram(ir: SequenceDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    alias_map: Dict[str, str] = {}
    declared_aliases: Set[str] = set()
    active_aliases: Set[str] = set()

    for index, participant in enumerate(ir.participants, 1):
        participant_name = _sanitize_name(participant.name)
        alias = re.sub(r"\W+", "", participant.alias.strip() or f"P{index}")
        if alias in declared_aliases:
            alias = f"P{index}_{participant_name[:3]}"
        declared_aliases.add(alias)
        alias_map[participant.name] = alias
        if participant.alias and participant.alias != participant.name:
            alias_map[participant.alias] = alias
        stereotype = f" <<{_sanitize_name(participant.stereotype)}>>" if participant.stereotype else ""
        lines.append(f"{participant.participant_type} {_quote(participant_name)} as {alias}{stereotype}")

    lines.append("")

    def _resolve(name: str) -> str:
        return alias_map.get(name, name)

    def _emit_message(message: MessageIR):
        sender = _resolve(message.sender)
        receiver = _resolve(message.receiver)
        label = _sanitize_label(message.label)
        if message.is_return:
            lines.append(f"{sender} -->> {receiver} : {label}")
        else:
            lines.append(f"{sender} -> {receiver} : {label}")

        if message.activate and receiver not in active_aliases:
            lines.append(f"activate {receiver}")
            active_aliases.add(receiver)
        if message.deactivate and sender in active_aliases:
            lines.append(f"deactivate {sender}")
            active_aliases.discard(sender)

    for message in ir.messages:
        _emit_message(message)

    for group in ir.groups:
        lines.append(f"{group.group_type} {_sanitize_label(group.label)}".rstrip())
        for message in group.messages:
            _emit_message(message)
        if group.else_messages:
            else_label = f" { _sanitize_label(group.else_label) }" if group.else_label else ""
            lines.append(f"else{else_label}".rstrip())
            for message in group.else_messages:
                _emit_message(message)
        lines.append("end")

    for alias in list(active_aliases):
        lines.append(f"deactivate {alias}")

    lines.append("")

    for note in ir.notes:
        target = _resolve(note.target)
        lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_activity_diagram(ir: ActivityDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    current_swimlane = ""

    def _switch_swimlane(swimlane: str):
        nonlocal current_swimlane
        if swimlane and swimlane != current_swimlane:
            lines.append(f"|{_sanitize_name(swimlane)}|")
            current_swimlane = swimlane

    def _emit_steps(steps: List[ActivityStepIR]):
        for step in steps:
            if step.swimlane:
                _switch_swimlane(step.swimlane)

            if step.step_type == "action":
                lines.append(f":{_sanitize_label(step.label) or 'Action'};")
            elif step.step_type == "decision":
                condition = _sanitize_label(step.condition) or "condition?"
                lines.append(f"if ({condition}) then (yes)")
                _emit_steps(step.yes_steps)
                if step.no_steps:
                    lines.append("else (no)")
                    _emit_steps(step.no_steps)
                lines.append("endif")
            elif step.step_type == "fork":
                lines.append("fork")
                lines.append(f"  :{_sanitize_label(step.label) or 'Parallel action'};")
                lines.append("fork again")
            elif step.step_type == "join":
                lines.append("end fork")
            elif step.step_type == "stop":
                lines.append("stop")

    if ir.swimlanes:
        _switch_swimlane(ir.swimlanes[0])

    lines.append("start")
    _emit_steps(ir.steps)

    if not any(step.step_type == "stop" for step in ir.steps):
        lines.append("stop")

    lines.append("")

    for note in ir.notes:
        lines.append(f"note {note.position} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_state_diagram(ir: StateDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    alias_map: Dict[str, str] = {}

    for index, state in enumerate(ir.states, 1):
        alias = f"S{index}"
        alias_map[state.name] = alias
        if state.display_name and state.display_name != state.name:
            alias_map[state.display_name] = alias
        display = state.display_name or _sanitize_name(state.name)
        lines.append(f"state {_quote(display)} as {alias}")
        if state.entry_action:
            lines.append(f"{alias} : entry / {_sanitize_label(state.entry_action)}")
        if state.do_action:
            lines.append(f"{alias} : do / {_sanitize_label(state.do_action)}")
        if state.exit_action:
            lines.append(f"{alias} : exit / {_sanitize_label(state.exit_action)}")

    lines.append("")

    def _resolve_state(name: str) -> str:
        if name == "[*]":
            return name
        return alias_map.get(name, _sanitize_name(name))

    for transition in ir.transitions:
        src = _resolve_state(transition.source)
        tgt = _resolve_state(transition.target)
        label_parts = []
        if transition.label:
            label_parts.append(_sanitize_label(transition.label))
        if transition.guard:
            label_parts.append(f"[{_sanitize_label(transition.guard)}]")
        suffix = f" : {' '.join(label_parts)}" if label_parts else ""
        lines.append(f"{src} --> {tgt}{suffix}")

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target, _sanitize_name(note.target))
        lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_component_diagram(ir: ComponentDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    alias_map: Dict[str, str] = {}
    counter = 1

    packages: Dict[str, List[ComponentIR]] = {}
    unpackaged: List[ComponentIR] = []
    for component in ir.components:
        if component.package.strip():
            packages.setdefault(component.package.strip(), []).append(component)
        else:
            unpackaged.append(component)

    def _emit_component(component: ComponentIR, indent: str = ""):
        nonlocal counter
        name = _sanitize_name(component.name)
        alias = f"COMP{counter}"
        counter += 1
        alias_map[component.name] = alias
        stereotype = f" <<{_sanitize_name(component.stereotype)}>>" if component.stereotype else ""
        lines.append(f"{indent}[{name}] as {alias}{stereotype}")

    for index, iface in enumerate(ir.interfaces, 1):
        alias = re.sub(r"\W+", "", iface.alias.strip() or f"I{index}")
        alias_map[iface.name] = alias
        if iface.alias and iface.alias != iface.name:
            alias_map[iface.alias] = alias
        lines.append(f"interface {_quote(_sanitize_name(iface.name))} as {alias}")

    lines.append("")

    for package_name, components in packages.items():
        lines.append(f"package {_quote(package_name)} {{")
        for component in components:
            _emit_component(component, indent="  ")
        lines.append("}")
        lines.append("")

    for component in unpackaged:
        _emit_component(component)

    if ir.external_components:
        lines.append("")
        lines.append("' External components")
        for component in ir.external_components:
            alias = f"COMP{counter}"
            counter += 1
            alias_map[component.name] = alias
            stereotype = _sanitize_name(component.stereotype or "External")
            lines.append(f"[{_sanitize_name(component.name)}] as {alias} <<{stereotype}>>")

    lines.append("")

    for rel in ir.relationships:
        src = alias_map.get(rel.source, rel.source)
        tgt = alias_map.get(rel.target, rel.target)
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        lines.append(f"{src} {_valid_arrow(rel.arrow_type)} {tgt}{label}")

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target, note.target)
        lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_package_diagram(ir: PackageDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    alias_map: Dict[str, str] = {}

    for pkg_index, package in enumerate(ir.packages, 1):
        package_alias = f"PKG{pkg_index}"
        alias_map[package.name] = package_alias
        lines.append(f"package {_quote(_sanitize_name(package.name))} as {package_alias} {{")
        for class_index, class_name in enumerate(package.classes[:5], 1):
            class_alias = f"{package_alias}_C{class_index}"
            alias_map[class_name] = class_alias
            lines.append(f"  class {_quote(_sanitize_name(class_name))} as {class_alias}")
        lines.append("}")
        lines.append("")

    for rel in ir.relationships:
        src = alias_map.get(rel.source)
        tgt = alias_map.get(rel.target)
        if not src or not tgt:
            log.warning("Package relationship references undeclared endpoint, skipping: %r -> %r", rel.source, rel.target)
            continue
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        lines.append(f"{src} {_valid_arrow(rel.arrow_type)} {tgt}{label}")

    lines.append("")

    for note in ir.notes:
        if note.target:
            target = alias_map.get(note.target)
            if not target:
                log.warning("Package note target not declared, skipping: %r", note.target)
                continue
            lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")
        else:
            lines.append(f"note {note.position} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def _deployment_child_keyword(child: DeploymentChildIR) -> str:
    mapping = {
        "artifact": "artifact",
        "component": "component",
        "database": "database",
    }
    return mapping.get(child.child_type, "artifact")


def compile_deployment_diagram(ir: DeploymentDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    alias_map: Dict[str, str] = {}
    child_counter = 1

    for node_index, node in enumerate(ir.nodes, 1):
        node_alias = f"N{node_index}"
        alias_map[node.name] = node_alias
        node_type = node.node_type if node.node_type in {"node", "database", "cloud", "artifact"} else "node"
        lines.append(f"{node_type} {_quote(_sanitize_name(node.name))} as {node_alias} {{")
        for child in node.children[:5]:
            child_alias = f"CH{child_counter}"
            child_counter += 1
            alias_map[child.name] = child_alias
            lines.append(
                f"  {_deployment_child_keyword(child)} {_quote(_sanitize_name(child.name))} as {child_alias}"
            )
        lines.append("}")
        lines.append("")

    for rel in ir.relationships:
        src = alias_map.get(rel.source)
        tgt = alias_map.get(rel.target)
        if not src or not tgt:
            log.warning("Deployment relationship references undeclared endpoint, skipping: %r -> %r", rel.source, rel.target)
            continue
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        lines.append(f"{src} {_valid_arrow(rel.arrow_type)} {tgt}{label}")

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target)
        if not target:
            log.warning("Deployment note target not declared, skipping: %r", note.target)
            continue
        lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def compile_navigation_diagram(ir: NavigationDiagramIR) -> str:
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f"title {_quote(ir.title)}")
    lines.append("")

    alias_map: Dict[str, str] = {}

    for index, screen in enumerate(ir.screens, 1):
        alias = f"SCR{index}"
        alias_map[screen.name] = alias
        if screen.display_name and screen.display_name != screen.name:
            alias_map[screen.display_name] = alias
        display = screen.display_name or _sanitize_name(screen.name)
        lines.append(f"state {_quote(display)} as {alias}")

    lines.append("")

    entry = alias_map.get(ir.entry_screen, "") if ir.entry_screen else ""
    if entry:
        lines.append(f"[*] --> {entry}")

    for transition in ir.transitions:
        src = "[*]" if transition.source == "[*]" else alias_map.get(transition.source, _sanitize_name(transition.source))
        tgt = "[*]" if transition.target == "[*]" else alias_map.get(transition.target, _sanitize_name(transition.target))
        label = f" : {_sanitize_label(transition.label)}" if transition.label else ""
        lines.append(f"{src} --> {tgt}{label}")

    for exit_screen in ir.exit_screens:
        resolved = alias_map.get(exit_screen, "")
        if resolved:
            lines.append(f"{resolved} --> [*]")

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target, note.target)
        lines.append(f"note {note.position} of {target} : {_sanitize_label(note.text)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


COMPILERS = {
    "class_diagram": compile_class_diagram,
    "usecase_diagram": compile_usecase_diagram,
    "sequence_diagram": compile_sequence_diagram,
    "activity_diagram": compile_activity_diagram,
    "state_diagram": compile_state_diagram,
    "component_diagram": compile_component_diagram,
    "package_diagram": compile_package_diagram,
    "deployment_diagram": compile_deployment_diagram,
    "navigation_diagram": compile_navigation_diagram,
}


def compile_ir(diagram_type: str, ir) -> str:
    compiler = COMPILERS.get(diagram_type)
    if compiler is None:
        raise ValueError(f"No compiler for diagram type: {diagram_type}")
    return compiler(ir)
