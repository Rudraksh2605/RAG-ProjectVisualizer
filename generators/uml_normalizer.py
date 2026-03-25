"""
UML IR normalizer.

Runs after JSON parsing and before validation. The goal is to make the IR more
consistent and closer to the intended UML semantics without guessing wildly.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from generators.uml_ir import (
    ClassDiagramIR,
    ClassIR,
    ComponentDiagramIR,
    ComponentIR,
    DeploymentChildIR,
    DeploymentDiagramIR,
    NavigationDiagramIR,
    PackageDiagramIR,
    ScreenIR,
    SequenceDiagramIR,
    StateDiagramIR,
    TransitionIR,
    UseCaseDiagramIR,
)

log = logging.getLogger("uml_normalizer")


def normalize_ir(diagram_type: str, ir, parsed_data: Optional[List[Dict]] = None):
    """Normalize an IR instance before validation."""
    normalizer = _NORMALIZERS.get(diagram_type)
    if normalizer is None:
        return ir
    if diagram_type == "navigation_diagram":
        return normalizer(ir, parsed_data)
    return normalizer(ir)


def normalize_class_diagram_ir(ir: ClassDiagramIR) -> ClassDiagramIR:
    """Promote undeclared relationship endpoints to external class stubs."""
    declared = {cls.name for cls in ir.classes}
    external = {cls.name for cls in ir.external_classes}

    for rel in ir.relationships:
        for endpoint in (rel.source, rel.target):
            if endpoint and endpoint not in declared and endpoint not in external:
                if _looks_like_valid_name(endpoint):
                    ir.external_classes.append(ClassIR(name=endpoint, stereotype="External"))
                    external.add(endpoint)
                    log.info("Promoted %r to external class stub", endpoint)

    return ir


def normalize_component_diagram_ir(ir: ComponentDiagramIR) -> ComponentDiagramIR:
    """Promote undeclared relationship endpoints to external component stubs."""
    declared = {c.name for c in ir.components}
    declared.update(i.name for i in ir.interfaces)
    declared.update(i.alias for i in ir.interfaces if i.alias)
    external = {c.name for c in ir.external_components}

    for rel in ir.relationships:
        for endpoint in (rel.source, rel.target):
            if endpoint and endpoint not in declared and endpoint not in external:
                if _looks_like_valid_name(endpoint):
                    ir.external_components.append(ComponentIR(name=endpoint, stereotype="External"))
                    external.add(endpoint)
                    log.info("Promoted %r to external component stub", endpoint)

    return ir


def normalize_usecase_diagram_ir(ir: UseCaseDiagramIR) -> UseCaseDiagramIR:
    """Canonicalize actor/use case references and normalize relation semantics."""
    ir.system_name = ir.system_name.strip() or "System"

    actor_lookup: Dict[str, str] = {}
    usecase_lookup: Dict[str, str] = {}

    cleaned_actors = []
    seen_actors: Set[str] = set()
    for actor in ir.actors:
        actor.name = actor.name.strip()
        actor.alias = _normalize_alias(actor.alias)
        if not actor.name:
            continue
        key = actor.name.lower()
        if key in seen_actors:
            continue
        seen_actors.add(key)
        cleaned_actors.append(actor)
        _register_lookup(actor_lookup, actor.name, actor.name)
        if actor.alias:
            _register_lookup(actor_lookup, actor.alias, actor.name)
    ir.actors = cleaned_actors

    cleaned_usecases = []
    seen_usecases: Set[str] = set()
    for usecase in ir.usecases:
        usecase.name = _collapse_whitespace(usecase.name)
        usecase.alias = _normalize_alias(usecase.alias)
        if not usecase.name:
            continue
        key = usecase.name.lower()
        if key in seen_usecases:
            continue
        seen_usecases.add(key)
        cleaned_usecases.append(usecase)
        _register_lookup(usecase_lookup, usecase.name, usecase.name)
        if usecase.alias:
            _register_lookup(usecase_lookup, usecase.alias, usecase.name)
    ir.usecases = cleaned_usecases

    def _resolve(ref: str) -> str:
        return _resolve_lookup(ref, actor_lookup, usecase_lookup)

    for rel in ir.relationships:
        rel.source = _resolve(rel.source)
        rel.target = _resolve(rel.target)
        relation_kind = _usecase_relation_kind(rel.label, rel.arrow_type)
        if relation_kind == "include":
            rel.label = "<<include>>"
            rel.arrow_type = "..>"
        elif relation_kind == "extend":
            rel.label = "<<extend>>"
            rel.arrow_type = "..>"
        elif relation_kind == "generalization":
            rel.label = ""
            rel.arrow_type = "--|>"
        else:
            if rel.label.strip().startswith("<<"):
                rel.label = ""
            rel.arrow_type = "-->"

    for note in ir.notes:
        note.target = _resolve(note.target)

    return ir


def normalize_sequence_diagram_ir(ir: SequenceDiagramIR) -> SequenceDiagramIR:
    """Resolve alias-like participant references in sequence messages."""
    if not ir.participants:
        return ir

    name_set: Set[str] = set()
    alias_to_name: Dict[str, str] = {}
    name_lower: Dict[str, str] = {}
    alias_lower: Dict[str, str] = {}
    initialism_map: Dict[str, str] = {}

    for participant in ir.participants:
        name_set.add(participant.name)
        name_lower[participant.name.lower()] = participant.name
        if participant.alias:
            alias_to_name[participant.alias] = participant.name
            alias_lower[participant.alias.lower()] = participant.name
        initials = _extract_initialism(participant.name)
        if len(initials) >= 2:
            initialism_map[initials] = participant.name

    def _resolve(endpoint: str) -> str:
        if not endpoint:
            return endpoint
        if endpoint in name_set:
            return endpoint
        if endpoint in alias_to_name:
            return alias_to_name[endpoint]
        lower = endpoint.lower()
        if lower in name_lower:
            return name_lower[lower]
        if lower in alias_lower:
            return alias_lower[lower]
        upper = endpoint.upper()
        if upper in initialism_map:
            return initialism_map[upper]
        return endpoint

    for message in ir.messages:
        message.sender = _resolve(message.sender)
        message.receiver = _resolve(message.receiver)
    for group in ir.groups:
        for message in group.messages:
            message.sender = _resolve(message.sender)
            message.receiver = _resolve(message.receiver)
        for message in group.else_messages:
            message.sender = _resolve(message.sender)
            message.receiver = _resolve(message.receiver)

    for note in ir.notes:
        note.target = _resolve(note.target)

    return ir


def normalize_state_diagram_ir(ir: StateDiagramIR) -> StateDiagramIR:
    """Canonicalize state references and add an initial transition when missing."""
    state_lookup: Dict[str, str] = {}
    cleaned_states = []
    seen_states: Set[str] = set()

    for state in ir.states:
        state.name = _collapse_whitespace(state.name)
        state.display_name = _collapse_whitespace(state.display_name) or _humanize_identifier(state.name)
        if not state.name:
            continue
        key = state.name.lower()
        if key in seen_states:
            continue
        seen_states.add(key)
        cleaned_states.append(state)
        _register_lookup(state_lookup, state.name, state.name)
        _register_lookup(state_lookup, state.display_name, state.name)
    ir.states = cleaned_states

    def _resolve_state(name: str) -> str:
        if name == "[*]":
            return name
        return _resolve_lookup(name, state_lookup)

    for transition in ir.transitions:
        transition.source = _resolve_state(transition.source)
        transition.target = _resolve_state(transition.target)

    for note in ir.notes:
        note.target = _resolve_state(note.target)

    if ir.states and not any(t.source == "[*]" for t in ir.transitions):
        preferred = _pick_initial_state_name(ir.states)
        ir.transitions.insert(0, TransitionIR(source="[*]", target=preferred, label="", guard=""))
        log.info("Injected initial transition to %r", preferred)

    return ir


def normalize_package_diagram_ir(ir: PackageDiagramIR) -> PackageDiagramIR:
    """Clean package/class names and canonicalize dependency endpoints."""
    package_lookup: Dict[str, str] = {}
    class_lookup: Dict[str, str] = {}
    cleaned_packages = []
    seen_packages: Set[str] = set()

    for package in ir.packages:
        package.name = _collapse_whitespace(package.name)
        if not package.name:
            continue
        package_key = package.name.lower()
        if package_key in seen_packages:
            continue
        seen_packages.add(package_key)
        seen_classes: Set[str] = set()
        cleaned_classes = []
        for class_name in package.classes:
            class_name = _collapse_whitespace(str(class_name))
            if not class_name:
                continue
            class_key = class_name.lower()
            if class_key in seen_classes:
                continue
            seen_classes.add(class_key)
            cleaned_classes.append(class_name)
            _register_lookup(class_lookup, class_name, class_name)
        package.classes = cleaned_classes
        cleaned_packages.append(package)
        _register_lookup(package_lookup, package.name, package.name)
    ir.packages = cleaned_packages

    def _resolve_declared(endpoint: str) -> str:
        resolved = _resolve_lookup(endpoint, package_lookup, class_lookup)
        if resolved != endpoint:
            return resolved
        if "." in endpoint:
            suffix = endpoint.rsplit(".", 1)[-1]
            resolved_suffix = _resolve_lookup(suffix, class_lookup)
            if resolved_suffix != suffix:
                return resolved_suffix
        return endpoint

    for rel in ir.relationships:
        rel.source = _resolve_declared(rel.source)
        rel.target = _resolve_declared(rel.target)

    for note in ir.notes:
        if note.target:
            note.target = _resolve_declared(note.target)

    return ir


def normalize_deployment_diagram_ir(ir: DeploymentDiagramIR) -> DeploymentDiagramIR:
    """Ensure undeclared endpoints can be addressed as node children."""
    node_names = {node.name for node in ir.nodes}
    child_names = {child.name for node in ir.nodes for child in node.children}
    all_declared = node_names | child_names

    for rel in ir.relationships:
        for endpoint in (rel.source, rel.target):
            if endpoint and endpoint not in all_declared and ir.nodes and _looks_like_valid_name(endpoint):
                ir.nodes[0].children.append(DeploymentChildIR(name=endpoint, child_type="artifact"))
                all_declared.add(endpoint)
                log.info("Promoted %r as deployment child of %r", endpoint, ir.nodes[0].name)

    return ir


def normalize_navigation_diagram_ir(
    ir: NavigationDiagramIR,
    parsed_data: Optional[List[Dict]] = None,
) -> NavigationDiagramIR:
    """Inject screens from parsed data and canonicalize navigation endpoints."""
    if (not ir.screens or len(ir.screens) < 2) and parsed_data:
        extracted = extract_screens_from_parsed_data(parsed_data)
        existing = {screen.name for screen in ir.screens}
        for screen in extracted:
            if screen.name not in existing:
                ir.screens.append(screen)
                existing.add(screen.name)
                log.info("Injected screen %r from parsed data", screen.name)

    screen_lookup: Dict[str, str] = {}
    cleaned_screens = []
    seen_screens: Set[str] = set()
    for screen in ir.screens:
        screen.name = _collapse_whitespace(screen.name)
        screen.display_name = _collapse_whitespace(screen.display_name) or _humanize_screen_name(screen.name)
        if not screen.name:
            continue
        key = screen.name.lower()
        if key in seen_screens:
            continue
        seen_screens.add(key)
        cleaned_screens.append(screen)
        _register_lookup(screen_lookup, screen.name, screen.name)
        _register_lookup(screen_lookup, screen.display_name, screen.name)
    ir.screens = cleaned_screens

    def _resolve_screen(name: str) -> str:
        if name == "[*]":
            return name
        return _resolve_lookup(name, screen_lookup)

    for transition in ir.transitions:
        transition.source = _resolve_screen(transition.source)
        transition.target = _resolve_screen(transition.target)

    for note in ir.notes:
        note.target = _resolve_screen(note.target)

    if ir.entry_screen:
        ir.entry_screen = _resolve_screen(ir.entry_screen)
    elif ir.transitions:
        starters = [t.target for t in ir.transitions if t.source == "[*]" and t.target != "[*]"]
        if starters:
            ir.entry_screen = starters[0]

    if not ir.entry_screen and ir.screens:
        preferred = _pick_entry_screen_name(ir.screens)
        ir.entry_screen = preferred

    canonical_exits = []
    seen_exits: Set[str] = set()
    if not ir.exit_screens:
        ir.exit_screens = [t.source for t in ir.transitions if t.target == "[*]" and t.source != "[*]"]
    for exit_screen in ir.exit_screens:
        resolved = _resolve_screen(exit_screen)
        if resolved and resolved != "[*]" and resolved.lower() not in seen_exits:
            seen_exits.add(resolved.lower())
            canonical_exits.append(resolved)
    ir.exit_screens = canonical_exits

    return ir


def extract_screens_from_parsed_data(parsed_data: List[Dict]) -> List[ScreenIR]:
    """Extract Activity and Fragment classes from parser output."""
    screens: List[ScreenIR] = []
    seen: Set[str] = set()

    for parsed_file in parsed_data:
        for cls in parsed_file.get("classes", []):
            component_type = cls.get("component_type", "")
            name = cls.get("name", "")
            if not name or component_type not in ("Activity", "Fragment"):
                continue
            if name in seen:
                continue
            screens.append(ScreenIR(name=name, display_name=_humanize_screen_name(name)))
            seen.add(name)

    return screens


def _looks_like_valid_name(name: str) -> bool:
    if not name or len(name) > 80:
        return False
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_. -]*$", name))


def _extract_initialism(name: str) -> str:
    return "".join(ch for ch in name if ch.isupper())


def _normalize_alias(alias: str) -> str:
    return re.sub(r"\W+", "", (alias or "").strip())


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _humanize_identifier(name: str) -> str:
    if not name:
        return ""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name.replace("_", " "))
    return _collapse_whitespace(spaced)


def _humanize_screen_name(name: str) -> str:
    display = name
    for suffix in ("Activity", "Fragment", "Screen", "Page"):
        if display.endswith(suffix) and len(display) > len(suffix):
            display = display[: -len(suffix)]
            break
    return _humanize_identifier(display)


def _register_lookup(lookup: Dict[str, str], raw_name: str, canonical_name: str):
    if not raw_name:
        return
    lookup[raw_name] = canonical_name
    lookup[raw_name.lower()] = canonical_name


def _resolve_lookup(name: str, *lookups: Dict[str, str]) -> str:
    if not name:
        return name
    for lookup in lookups:
        if name in lookup:
            return lookup[name]
        lowered = name.lower()
        if lowered in lookup:
            return lookup[lowered]
    return name


def _usecase_relation_kind(label: str, arrow_type: str) -> str:
    text = f"{label} {arrow_type}".lower()
    if "include" in text:
        return "include"
    if "extend" in text:
        return "extend"
    if "general" in text or "|>" in arrow_type:
        return "generalization"
    return "association"


def _pick_initial_state_name(states) -> str:
    preferred_keywords = ("idle", "initial", "created", "new", "ready")
    for state in states:
        lowered = state.name.lower()
        if any(keyword in lowered for keyword in preferred_keywords):
            return state.name
    return states[0].name


def _pick_entry_screen_name(screens: List[ScreenIR]) -> str:
    preferred_keywords = ("main", "home", "splash", "launcher", "login", "start")
    for screen in screens:
        lowered = screen.name.lower()
        if any(keyword in lowered for keyword in preferred_keywords):
            return screen.name
    return screens[0].name


_NORMALIZERS = {
    "class_diagram": normalize_class_diagram_ir,
    "component_diagram": normalize_component_diagram_ir,
    "usecase_diagram": normalize_usecase_diagram_ir,
    "sequence_diagram": normalize_sequence_diagram_ir,
    "state_diagram": normalize_state_diagram_ir,
    "package_diagram": normalize_package_diagram_ir,
    "deployment_diagram": normalize_deployment_diagram_ir,
    "navigation_diagram": normalize_navigation_diagram_ir,
}
