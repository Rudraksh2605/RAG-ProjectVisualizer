"""
UML IR Normalizer — diagram-type-aware normalization before validation.

Inserted between parse_ir() and validate_ir() in the pipeline.
Performs deterministic transformations to reduce IR validation failures:
  - Promotes undeclared relationship endpoints to external stubs
  - Resolves alias-like message senders/receivers to canonical names
  - Injects screens from parsed project data for navigation diagrams
  - Ensures deployment children are properly addressable

Design rule: normalizers MAY mutate the IR in-place. They do NOT
validate — that is the validator's job.
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict, Optional, Any, Set

from generators.uml_ir import (
    ClassDiagramIR, ClassIR,
    ComponentDiagramIR, ComponentIR,
    SequenceDiagramIR, MessageIR,
    DeploymentDiagramIR, DeploymentChildIR,
    NavigationDiagramIR, ScreenIR, TransitionIR,
)

log = logging.getLogger("uml_normalizer")


# ═══════════════════════════════════════════════════════════════
#  Dispatcher
# ═══════════════════════════════════════════════════════════════

def normalize_ir(diagram_type: str, ir, parsed_data: Optional[List[Dict]] = None):
    """
    Normalize an IR instance before validation.

    Returns the (possibly mutated) IR.
    """
    normalizer = _NORMALIZERS.get(diagram_type)
    if normalizer is None:
        return ir

    if diagram_type == "navigation_diagram":
        return normalizer(ir, parsed_data)
    return normalizer(ir)


# ═══════════════════════════════════════════════════════════════
#  Class Diagram Normalization
# ═══════════════════════════════════════════════════════════════

def normalize_class_diagram_ir(ir: ClassDiagramIR) -> ClassDiagramIR:
    """
    Promote undeclared relationship endpoints to external_classes.

    If a relationship references a class not in ir.classes and not already
    in ir.external_classes, create a lightweight stub with <<External>>.
    """
    declared = {cls.name for cls in ir.classes}
    external = {cls.name for cls in ir.external_classes}

    for rel in ir.relationships:
        for endpoint in (rel.source, rel.target):
            if not endpoint or not endpoint.strip():
                continue
            if endpoint not in declared and endpoint not in external:
                if _looks_like_valid_name(endpoint):
                    ir.external_classes.append(ClassIR(
                        name=endpoint,
                        stereotype="External",
                    ))
                    external.add(endpoint)
                    log.info("Promoted '%s' to external class stub", endpoint)

    return ir


# ═══════════════════════════════════════════════════════════════
#  Component Diagram Normalization
# ═══════════════════════════════════════════════════════════════

def normalize_component_diagram_ir(ir: ComponentDiagramIR) -> ComponentDiagramIR:
    """
    Promote undeclared relationship endpoints to external_components.
    """
    declared = {c.name for c in ir.components}
    declared.update(i.name for i in ir.interfaces)
    declared.update(i.alias for i in ir.interfaces if i.alias)
    external = {c.name for c in ir.external_components}

    for rel in ir.relationships:
        for endpoint in (rel.source, rel.target):
            if not endpoint or not endpoint.strip():
                continue
            if endpoint not in declared and endpoint not in external:
                if _looks_like_valid_name(endpoint):
                    ir.external_components.append(ComponentIR(
                        name=endpoint,
                        stereotype="External",
                    ))
                    external.add(endpoint)
                    log.info("Promoted '%s' to external component stub", endpoint)

    return ir


# ═══════════════════════════════════════════════════════════════
#  Sequence Diagram Normalization
# ═══════════════════════════════════════════════════════════════

def normalize_sequence_diagram_ir(ir: SequenceDiagramIR) -> SequenceDiagramIR:
    """
    Resolve alias-like message senders/receivers to canonical participant names.

    Matching strategies (in priority order):
      1. Exact name match (already valid)
      2. Exact alias match → rewrite to name
      3. Case-insensitive name match
      4. Case-insensitive alias match
      5. Initialism match (e.g. "LA" → "LoginActivity")
    """
    if not ir.participants:
        return ir

    # Build lookup tables
    name_set: Set[str] = set()
    alias_to_name: Dict[str, str] = {}
    name_lower: Dict[str, str] = {}    # lowercase → canonical name
    alias_lower: Dict[str, str] = {}   # lowercase alias → canonical name
    initialism_map: Dict[str, str] = {}  # uppercase initialism → canonical name

    for p in ir.participants:
        name_set.add(p.name)
        name_lower[p.name.lower()] = p.name
        if p.alias:
            alias_to_name[p.alias] = p.name
            alias_lower[p.alias.lower()] = p.name
        # Build initialism: "LoginActivity" → "LA"
        initials = _extract_initialism(p.name)
        if initials and len(initials) >= 2:
            initialism_map[initials] = p.name

    def _resolve(endpoint: str) -> str:
        if not endpoint:
            return endpoint
        # 1. Exact name match
        if endpoint in name_set:
            return endpoint
        # 2. Exact alias match
        if endpoint in alias_to_name:
            resolved = alias_to_name[endpoint]
            log.info("Resolved alias '%s' → '%s'", endpoint, resolved)
            return resolved
        # 3. Case-insensitive name match
        lower = endpoint.lower()
        if lower in name_lower:
            resolved = name_lower[lower]
            log.info("Resolved case-insensitive '%s' → '%s'", endpoint, resolved)
            return resolved
        # 4. Case-insensitive alias match
        if lower in alias_lower:
            resolved = alias_lower[lower]
            log.info("Resolved case-insensitive alias '%s' → '%s'", endpoint, resolved)
            return resolved
        # 5. Initialism match
        upper = endpoint.upper()
        if upper in initialism_map:
            resolved = initialism_map[upper]
            log.info("Resolved initialism '%s' → '%s'", endpoint, resolved)
            return resolved
        # No match — leave as-is for validator to catch
        return endpoint

    def _resolve_messages(msgs: List[MessageIR]):
        for msg in msgs:
            msg.sender = _resolve(msg.sender)
            msg.receiver = _resolve(msg.receiver)

    _resolve_messages(ir.messages)
    for grp in ir.groups:
        _resolve_messages(grp.messages)
        _resolve_messages(grp.else_messages)

    return ir


# ═══════════════════════════════════════════════════════════════
#  Deployment Diagram Normalization
# ═══════════════════════════════════════════════════════════════

def normalize_deployment_diagram_ir(ir: DeploymentDiagramIR) -> DeploymentDiagramIR:
    """
    Ensure relationship endpoints that reference child artifacts are valid.

    If a relationship references something not in top-level nodes but present
    as a child, it's already valid. If it references neither, promote it to
    a child of the most likely parent node (or first node).
    """
    node_names = {n.name for n in ir.nodes}
    child_names: Dict[str, str] = {}  # child name → parent node name
    for node in ir.nodes:
        for child in node.children:
            child_names[child.name] = node.name

    all_declared = node_names | set(child_names.keys())

    for rel in ir.relationships:
        for endpoint in (rel.source, rel.target):
            if not endpoint or not endpoint.strip():
                continue
            if endpoint not in all_declared:
                if _looks_like_valid_name(endpoint) and ir.nodes:
                    # Promote as child of first node
                    parent = ir.nodes[0]
                    parent.children.append(DeploymentChildIR(
                        name=endpoint, child_type="artifact"
                    ))
                    all_declared.add(endpoint)
                    log.info("Promoted '%s' as child of '%s'", endpoint, parent.name)

    return ir


# ═══════════════════════════════════════════════════════════════
#  Navigation Diagram Normalization
# ═══════════════════════════════════════════════════════════════

def normalize_navigation_diagram_ir(
    ir: NavigationDiagramIR,
    parsed_data: Optional[List[Dict]] = None,
) -> NavigationDiagramIR:
    """
    Deterministically inject screens from parsed project data.

    If the LLM returned no screens (or very few), extract Activity/Fragment
    classes from the parsed data and add them.
    """
    if ir.screens and len(ir.screens) >= 2:
        # LLM provided enough screens — skip injection
        return ir

    if not parsed_data:
        log.warning("No parsed data available for navigation screen extraction")
        return ir

    # Extract screens from parsed data
    extracted = extract_screens_from_parsed_data(parsed_data)
    if not extracted:
        log.warning("No Activity/Fragment classes found in parsed data")
        return ir

    existing_names = {s.name for s in ir.screens}

    for screen in extracted:
        if screen.name not in existing_names:
            ir.screens.append(screen)
            existing_names.add(screen.name)
            log.info("Injected screen '%s' from parsed data", screen.name)

    # Set entry_screen if not set
    if not ir.entry_screen and ir.screens:
        # Prefer something with "main", "splash", or "launcher" in name
        for s in ir.screens:
            lower = s.name.lower()
            if any(kw in lower for kw in ("main", "splash", "launcher", "home")):
                ir.entry_screen = s.name
                break
        if not ir.entry_screen:
            ir.entry_screen = ir.screens[0].name

    return ir


def extract_screens_from_parsed_data(parsed_data: List[Dict]) -> List[ScreenIR]:
    """
    Extract Activity and Fragment classes from parser output as ScreenIR instances.
    """
    screens: List[ScreenIR] = []
    seen: Set[str] = set()

    for pf in parsed_data:
        for cls in pf.get("classes", []):
            ctype = cls.get("component_type", "")
            name = cls.get("name", "")
            if not name:
                continue
            if ctype in ("Activity", "Fragment") and name not in seen:
                # Build display name: "LoginActivity" → "Login"
                display = name
                for suffix in ("Activity", "Fragment"):
                    if display.endswith(suffix) and len(display) > len(suffix):
                        display = display[:-len(suffix)]
                        break
                screens.append(ScreenIR(name=name, display_name=display))
                seen.add(name)

    return screens


# ═══════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════

def _looks_like_valid_name(name: str) -> bool:
    """Check that a name looks like a real class/component identifier."""
    if not name or len(name) < 1 or len(name) > 80:
        return False
    # Must start with a letter, contain only word chars and common separators
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9_. -]*$', name))


def _extract_initialism(name: str) -> str:
    """Extract uppercase initialism from a CamelCase name.

    "LoginActivity" → "LA", "FirebaseAuth" → "FA"
    """
    return ''.join(c for c in name if c.isupper())


# ═══════════════════════════════════════════════════════════════
#  Normalizer registry
# ═══════════════════════════════════════════════════════════════

_NORMALIZERS = {
    "class_diagram": normalize_class_diagram_ir,
    "component_diagram": normalize_component_diagram_ir,
    "sequence_diagram": normalize_sequence_diagram_ir,
    "deployment_diagram": normalize_deployment_diagram_ir,
    "navigation_diagram": normalize_navigation_diagram_ir,
}
