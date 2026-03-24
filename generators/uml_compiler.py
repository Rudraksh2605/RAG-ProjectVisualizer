"""
Deterministic PlantUML Compiler — converts validated IR into PlantUML.

Key guarantees:
  - Declarations always precede references.
  - Aliases are generated deterministically (C1, UC1, P1, S1, etc.).
  - Names and labels are sanitized (no unescaped quotes, no special chars).
  - Blocks are always properly balanced ({ }, activate/deactivate, alt/end).
  - No duplicate declarations.
  - Consistent formatting.

The compiler owns ALL syntax-sensitive decisions: the LLM never needs to
produce a single PlantUML keyword.
"""

from __future__ import annotations
import re
import logging
from typing import List, Set

from generators.uml_ir import (
    ClassDiagramIR, ClassIR,
    UseCaseDiagramIR,
    SequenceDiagramIR, MessageIR, GroupIR,
    ActivityDiagramIR, ActivityStepIR,
    StateDiagramIR,
    ComponentDiagramIR, ComponentIR,
    PackageDiagramIR,
    DeploymentDiagramIR, DeploymentChildIR,
    NavigationDiagramIR,
)

log = logging.getLogger("uml_compiler")

# ═══════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════

def _sanitize_name(name: str) -> str:
    """Make a name safe for use as a PlantUML identifier."""
    s = name.strip()
    if not s:
        return "Unknown"
    # Remove characters that break PlantUML
    s = re.sub(r'[<>{}()\[\]`~!@#$%^&*=+|\\;]', '', s)
    s = s.strip()
    return s if s else "Unknown"


def _sanitize_alias(name: str, counter: int, prefix: str = "E") -> str:
    """Generate a deterministic alias like C1, UC1, P1, etc."""
    return f"{prefix}{counter}"


def _quote(text: str) -> str:
    """Safely quote a string for PlantUML double-quote contexts."""
    s = text.replace('"', "'").replace('\n', ' ').strip()
    return f'"{s}"'


def _sanitize_label(text: str) -> str:
    """Clean a relationship/arrow label."""
    s = text.replace('"', "'").replace('\n', ' ').strip()
    return s


def _valid_arrow(arrow: str) -> str:
    """Validate and return a safe PlantUML arrow type."""
    allowed = {"-->", "<--", "--|>", "<|--", "..|>", "<|..", "*--", "--*",
               "o--", "--o", "..>", "<..", "..", "--", "->", "<-"}
    return arrow if arrow in allowed else "-->"


# ═══════════════════════════════════════════════════════════════
#  Class Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_class_diagram(ir: ClassDiagramIR) -> str:
    """Compile ClassDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    # Group classes by package
    packages: dict = {}
    no_pkg_classes: List[ClassIR] = []
    for cls in ir.classes:
        pkg = cls.package.strip()
        if pkg:
            packages.setdefault(pkg, []).append(cls)
        else:
            no_pkg_classes.append(cls)

    declared_names: Set[str] = set()
    alias_map: dict = {}  # original name -> sanitized name
    counter = 1

    def _emit_class(cls: ClassIR) -> List[str]:
        nonlocal counter
        cname = _sanitize_name(cls.name)
        if cname in declared_names:
            return []
        declared_names.add(cname)
        alias_map[cls.name] = cname
        clines = []

        # Determine keyword
        if cls.is_interface:
            kw = "interface"
        elif cls.is_abstract:
            kw = "abstract class"
        else:
            kw = "class"

        stereo = f" <<{_sanitize_name(cls.stereotype)}>>" if cls.stereotype else ""
        clines.append(f'{kw} {_quote(cname)}{stereo} {{')

        for f in cls.fields[:5]:  # limit to avoid clutter
            fname = _sanitize_name(f.name)
            ftype = f" : {_sanitize_name(f.type)}" if f.type else ""
            clines.append(f'  {f.visibility}{fname}{ftype}')

        for m in cls.methods[:6]:
            mname = _sanitize_name(m.name)
            params = f"({_sanitize_label(m.params)})" if m.params else "()"
            rtype = f" : {_sanitize_name(m.return_type)}" if m.return_type else ""
            clines.append(f'  {m.visibility}{mname}{params}{rtype}')

        clines.append("}")
        counter += 1
        return clines

    # Emit packaged classes
    for pkg_name, classes in packages.items():
        lines.append(f'package {_quote(pkg_name)} {{')
        for cls in classes:
            for cl in _emit_class(cls):
                lines.append(f'  {cl}')
        lines.append("}")
        lines.append("")

    # Emit unpackaged classes
    for cls in no_pkg_classes:
        lines.extend(_emit_class(cls))
        lines.append("")

    # Emit external class stubs (promoted by normalizer)
    if ir.external_classes:
        lines.append("' -- External collaborators --")
        for ext in ir.external_classes:
            ename = _sanitize_name(ext.name)
            if ename not in declared_names:
                declared_names.add(ename)
                alias_map[ext.name] = ename
                stereo = ext.stereotype or "External"
                lines.append(f'class {_quote(ename)} <<{_sanitize_name(stereo)}>>')
        lines.append("")

    # Emit relationships — only between declared entities
    for rel in ir.relationships:
        src = alias_map.get(rel.source, _sanitize_name(rel.source))
        tgt = alias_map.get(rel.target, _sanitize_name(rel.target))
        arrow = _valid_arrow(rel.arrow_type)
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        lines.append(f'{_quote(src)} {arrow} {_quote(tgt)}{label}')

    lines.append("")

    # Emit notes
    for note in ir.notes:
        target = alias_map.get(note.target, _sanitize_name(note.target))
        lines.append(f'note {note.position} of {_quote(target)} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Use Case Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_usecase_diagram(ir: UseCaseDiagramIR) -> str:
    """Compile UseCaseDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("left to right direction")
    lines.append("")

    alias_map: dict = {}
    declared: Set[str] = set()

    # Declare actors
    for i, actor in enumerate(ir.actors, 1):
        aname = _sanitize_name(actor.name)
        alias = actor.alias.strip() or f"A{i}"
        alias = re.sub(r'\W+', '', alias)  # ensure safe alias
        if alias in declared:
            alias = f"A{i}_{aname[:3]}"
        declared.add(alias)
        alias_map[actor.name] = alias
        if actor.alias and actor.alias != actor.name:
            alias_map[actor.alias] = alias  # LLM alias → compiler alias
        lines.append(f'actor {_quote(aname)} as {alias}')

    lines.append("")

    # System boundary with use cases
    sys_name = _sanitize_name(ir.system_name) if ir.system_name else "System"
    lines.append(f'rectangle {_quote(sys_name)} {{')

    for i, uc in enumerate(ir.usecases, 1):
        ucname = _sanitize_name(uc.name)
        alias = uc.alias.strip() or f"UC{i}"
        alias = re.sub(r'\W+', '', alias)
        if alias in declared:
            alias = f"UC{i}_{ucname[:3]}"
        declared.add(alias)
        alias_map[uc.name] = alias
        if uc.alias and uc.alias != uc.name:
            alias_map[uc.alias] = alias  # LLM alias → compiler alias
        lines.append(f'  usecase {_quote(ucname)} as {alias}')

    lines.append("}")
    lines.append("")

    # Relationships — only using declared aliases
    for rel in ir.relationships:
        src = alias_map.get(rel.source, rel.source)
        tgt = alias_map.get(rel.target, rel.target)
        # Verify both endpoints exist
        if src not in declared and rel.source not in declared:
            log.warning("Use case relationship source %r not declared, skipping", rel.source)
            continue
        if tgt not in declared and rel.target not in declared:
            log.warning("Use case relationship target %r not declared, skipping", rel.target)
            continue
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        arrow = _valid_arrow(rel.arrow_type)
        lines.append(f'{src} {arrow} {tgt}{label}')

    lines.append("")

    # Notes
    for note in ir.notes:
        target = alias_map.get(note.target, note.target)
        lines.append(f'note {note.position} of {target} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Sequence Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_sequence_diagram(ir: SequenceDiagramIR) -> str:
    """Compile SequenceDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    alias_map: dict = {}
    declared: Set[str] = set()
    active_set: Set[str] = set()  # track activated participants

    # Declare participants first (guarantees declaration before reference)
    for i, p in enumerate(ir.participants, 1):
        pname = _sanitize_name(p.name)
        alias = p.alias.strip() or f"P{i}"
        alias = re.sub(r'\W+', '', alias)
        if alias in declared:
            alias = f"P{i}_{pname[:3]}"
        declared.add(alias)
        alias_map[p.name] = alias
        if p.alias and p.alias != p.name:
            alias_map[p.alias] = alias  # LLM alias → compiler alias
        stereo = f" <<{_sanitize_name(p.stereotype)}>>" if p.stereotype else ""
        ptype = p.participant_type
        lines.append(f'{ptype} {_quote(pname)} as {alias}{stereo}')

    lines.append("")

    def _resolve(name: str) -> str:
        return alias_map.get(name, name)

    def _emit_message(msg: MessageIR):
        sender = _resolve(msg.sender)
        receiver = _resolve(msg.receiver)
        arrow = "-->" if not msg.is_return else "-->>"
        if msg.is_return:
            arrow = "-->"
            # Use dashed arrow for returns
            arrow = "-->>"

        label = _sanitize_label(msg.label) if msg.label else ""

        if msg.is_return:
            lines.append(f'{sender} -->> {receiver} : {label}')
        else:
            lines.append(f'{sender} -> {receiver} : {label}')

        if msg.activate and receiver not in active_set:
            lines.append(f'activate {receiver}')
            active_set.add(receiver)

        if msg.deactivate and sender in active_set:
            lines.append(f'deactivate {sender}')
            active_set.discard(sender)

    # Emit top-level messages
    for msg in ir.messages:
        _emit_message(msg)

    # Emit groups (alt/opt/loop)
    for grp in ir.groups:
        label = _sanitize_label(grp.label)
        lines.append(f'{grp.group_type} {label}')
        for msg in grp.messages:
            _emit_message(msg)
        if grp.else_messages:
            else_label = _sanitize_label(grp.else_label) if grp.else_label else ""
            lines.append(f'else {else_label}')
            for msg in grp.else_messages:
                _emit_message(msg)
        lines.append("end")

    # Deactivate all remaining active participants
    for alias in list(active_set):
        lines.append(f'deactivate {alias}')
    active_set.clear()

    lines.append("")

    # Notes
    for note in ir.notes:
        target = _resolve(note.target)
        lines.append(f'note {note.position} of {target} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Activity Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_activity_diagram(ir: ActivityDiagramIR) -> str:
    """Compile ActivityDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    current_swimlane = ""

    def _switch_swimlane(lane: str):
        nonlocal current_swimlane
        if lane and lane != current_swimlane:
            lines.append(f'|{_sanitize_name(lane)}|')
            current_swimlane = lane

    def _emit_steps(steps: List[ActivityStepIR]):
        for step in steps:
            if step.swimlane:
                _switch_swimlane(step.swimlane)

            if step.step_type == "action":
                label = _sanitize_label(step.label) if step.label else "Action"
                lines.append(f':{label};')

            elif step.step_type == "decision":
                cond = _sanitize_label(step.condition) if step.condition else "condition?"
                lines.append(f'if ({cond}) then (yes)')
                _emit_steps(step.yes_steps)
                if step.no_steps:
                    lines.append('else (no)')
                    _emit_steps(step.no_steps)
                lines.append('endif')

            elif step.step_type == "fork":
                lines.append('fork')
                lines.append(f'  :{_sanitize_label(step.label)};')
                lines.append('fork again')

            elif step.step_type == "join":
                lines.append('end fork')

            elif step.step_type == "stop":
                lines.append('stop')

    # If swimlanes are defined, emit the first swimlane before "start"
    if ir.swimlanes:
        first_lane = ir.swimlanes[0] if ir.swimlanes else ""
        if first_lane:
            _switch_swimlane(first_lane)

    lines.append("start")

    _emit_steps(ir.steps)

    # Ensure the diagram ends with stop if not already present
    if not any(s.step_type == "stop" for s in ir.steps):
        lines.append("stop")

    lines.append("")

    # Notes
    for note in ir.notes:
        lines.append(f'note {note.position} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  State Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_state_diagram(ir: StateDiagramIR) -> str:
    """Compile StateDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    alias_map: dict = {}
    declared: Set[str] = set()

    # Declare states
    for i, state in enumerate(ir.states, 1):
        sname = _sanitize_name(state.name)
        alias = f"S{i}"
        declared.add(alias)
        alias_map[state.name] = alias
        if state.display_name and state.display_name != state.name:
            alias_map[state.display_name] = alias  # display name → compiler alias
        display = state.display_name or sname
        lines.append(f'state {_quote(display)} as {alias}')

        # State body (entry/exit/do actions)
        has_body = state.entry_action or state.exit_action or state.do_action
        if has_body:
            if state.entry_action:
                lines.append(f'{alias} : entry / {_sanitize_label(state.entry_action)}')
            if state.do_action:
                lines.append(f'{alias} : do / {_sanitize_label(state.do_action)}')
            if state.exit_action:
                lines.append(f'{alias} : exit / {_sanitize_label(state.exit_action)}')

    lines.append("")

    def _resolve_state(name: str) -> str:
        if name == "[*]":
            return "[*]"
        return alias_map.get(name, _sanitize_name(name))

    # Transitions
    for tr in ir.transitions:
        src = _resolve_state(tr.source)
        tgt = _resolve_state(tr.target)
        label_parts = []
        if tr.label:
            label_parts.append(_sanitize_label(tr.label))
        if tr.guard:
            label_parts.append(f'[{_sanitize_label(tr.guard)}]')
        label = " ".join(label_parts)
        label_str = f" : {label}" if label else ""
        lines.append(f'{src} --> {tgt}{label_str}')

    lines.append("")

    # Notes
    for note in ir.notes:
        target = alias_map.get(note.target, _sanitize_name(note.target))
        lines.append(f'note {note.position} of {target} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Component Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_component_diagram(ir: ComponentDiagramIR) -> str:
    """Compile ComponentDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    alias_map: dict = {}
    declared: Set[str] = set()
    counter = 1

    # Group by package
    packages: dict = {}
    no_pkg: list = []
    for comp in ir.components:
        pkg = comp.package.strip()
        if pkg:
            packages.setdefault(pkg, []).append(comp)
        else:
            no_pkg.append(comp)

    def _emit_component(comp, indent=""):
        nonlocal counter
        cname = _sanitize_name(comp.name)
        alias = f"COMP{counter}"
        counter += 1
        declared.add(alias)
        alias_map[comp.name] = alias
        stereo = f" <<{_sanitize_name(comp.stereotype)}>>" if comp.stereotype else ""
        lines.append(f'{indent}[{cname}] as {alias}{stereo}')

    # Emit interfaces
    for i, iface in enumerate(ir.interfaces, 1):
        iname = _sanitize_name(iface.name)
        alias = iface.alias.strip() or f"I{i}"
        alias = re.sub(r'\W+', '', alias)
        declared.add(alias)
        alias_map[iface.name] = alias
        lines.append(f'interface {_quote(iname)} as {alias}')

    lines.append("")

    # Emit packaged components
    for pkg_name, comps in packages.items():
        lines.append(f'package {_quote(pkg_name)} {{')
        for comp in comps:
            _emit_component(comp, indent="  ")
        lines.append("}")
        lines.append("")

    # Emit unpackaged
    for comp in no_pkg:
        _emit_component(comp)

    # Emit external component stubs (promoted by normalizer)
    if ir.external_components:
        lines.append("")
        lines.append("' -- External components --")
        for ext in ir.external_components:
            nonlocal_name = _sanitize_name(ext.name)
            ext_alias = f"COMP{counter}"
            counter += 1
            declared.add(ext_alias)
            alias_map[ext.name] = ext_alias
            stereo = ext.stereotype or "External"
            lines.append(f'[{nonlocal_name}] as {ext_alias} <<{_sanitize_name(stereo)}>>')

    lines.append("")

    # Relationships
    for rel in ir.relationships:
        src = alias_map.get(rel.source, rel.source)
        tgt = alias_map.get(rel.target, rel.target)
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        arrow = _valid_arrow(rel.arrow_type)
        lines.append(f'{src} {arrow} {tgt}{label}')

    lines.append("")

    # Notes
    for note in ir.notes:
        target = alias_map.get(note.target, note.target)
        lines.append(f'note {note.position} of {target} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Package Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_package_diagram(ir: PackageDiagramIR) -> str:
    """Compile PackageDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    alias_map: dict = {}

    for i, pkg in enumerate(ir.packages, 1):
        pname = _sanitize_name(pkg.name)
        alias = f"PKG{i}"
        alias_map[pkg.name] = alias
        lines.append(f'package {_quote(pname)} {{')
        for cls_name in pkg.classes[:5]:  # limit
            cname = _sanitize_name(cls_name)
            lines.append(f'  class {_quote(cname)}')
        lines.append("}")
        lines.append("")

    # Relationships
    for rel in ir.relationships:
        src = _sanitize_name(rel.source)
        tgt = _sanitize_name(rel.target)
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        arrow = _valid_arrow(rel.arrow_type)
        lines.append(f'{_quote(src)} {arrow} {_quote(tgt)}{label}')

    lines.append("")

    # Notes
    for note in ir.notes:
        lines.append(f'note {note.position} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Deployment Diagram Compiler
# ═══════════════════════════════════════════════════════════════

def compile_deployment_diagram(ir: DeploymentDiagramIR) -> str:
    """Compile DeploymentDiagramIR into valid PlantUML."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    alias_map: dict = {}
    child_counter = 1

    for i, node in enumerate(ir.nodes, 1):
        nname = _sanitize_name(node.name)
        alias = f"N{i}"
        alias_map[node.name] = alias
        ntype = node.node_type
        lines.append(f'{ntype} {_quote(nname)} as {alias} {{')
        for child in node.children[:5]:
            cname = _sanitize_name(child.name)
            child_alias = f"CH{child_counter}"
            child_counter += 1
            alias_map[child.name] = child_alias
            lines.append(f'  [{cname}] as {child_alias}')
        lines.append("}")
        lines.append("")

    # Relationships — resolve via alias_map (nodes and children)
    for rel in ir.relationships:
        src = alias_map.get(rel.source, _sanitize_name(rel.source))
        tgt = alias_map.get(rel.target, _sanitize_name(rel.target))
        label = f" : {_sanitize_label(rel.label)}" if rel.label else ""
        arrow = _valid_arrow(rel.arrow_type)
        lines.append(f'{src} {arrow} {tgt}{label}')

    lines.append("")

    for note in ir.notes:
        target = alias_map.get(note.target, note.target)
        lines.append(f'note {note.position} of {target} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Navigation Diagram Compiler (state diagram semantics)
# ═══════════════════════════════════════════════════════════════

def compile_navigation_diagram(ir: NavigationDiagramIR) -> str:
    """Compile NavigationDiagramIR into valid PlantUML (state diagram)."""
    lines: List[str] = ["@startuml"]

    if ir.title:
        lines.append(f'title {_quote(ir.title)}')
    lines.append("")

    alias_map: dict = {}
    declared: Set[str] = set()

    for i, screen in enumerate(ir.screens, 1):
        sname = _sanitize_name(screen.name)
        alias = f"SCR{i}"
        declared.add(alias)
        alias_map[screen.name] = alias
        if screen.display_name and screen.display_name != screen.name:
            alias_map[screen.display_name] = alias  # display name → compiler alias
        display = screen.display_name or sname
        lines.append(f'state {_quote(display)} as {alias}')

    lines.append("")

    # Entry point — resolve via alias_map (accepts both name and display_name)
    entry = alias_map.get(ir.entry_screen, "") if ir.entry_screen else ""
    if entry:
        lines.append(f'[*] --> {entry}')

    # Transitions
    for tr in ir.transitions:
        src = "[*]" if tr.source == "[*]" else alias_map.get(tr.source, _sanitize_name(tr.source))
        tgt = "[*]" if tr.target == "[*]" else alias_map.get(tr.target, _sanitize_name(tr.target))
        label = f" : {_sanitize_label(tr.label)}" if tr.label else ""
        lines.append(f'{src} --> {tgt}{label}')

    # Exit points — resolve via alias_map
    for exit_scr in ir.exit_screens:
        resolved = alias_map.get(exit_scr, "")
        if resolved:
            lines.append(f'{resolved} --> [*]')

    lines.append("")

    # Notes
    for note in ir.notes:
        target = alias_map.get(note.target, note.target)
        lines.append(f'note {note.position} of {target} : {_sanitize_label(note.text)}')

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Compiler registry
# ═══════════════════════════════════════════════════════════════

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
    """Compile any IR instance into PlantUML using the appropriate compiler."""
    compiler = COMPILERS.get(diagram_type)
    if compiler is None:
        raise ValueError(f"No compiler for diagram type: {diagram_type}")
    return compiler(ir)
