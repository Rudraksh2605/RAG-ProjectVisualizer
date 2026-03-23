"""
UML Intermediate Representation (IR) — structured data models.

Instead of asking the LLM to produce raw PlantUML syntax, we ask it to
produce JSON conforming to these schemas.  A deterministic compiler then
converts validated IR into guaranteed-correct PlantUML.

Each diagram type has:
  - A set of dataclasses that define the IR contract.
  - A JSON-schema-like description string for prompt injection.
  - A ``from_dict`` factory that parses raw dicts (from LLM JSON) into
    typed dataclass instances, with graceful defaults for missing fields.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ═══════════════════════════════════════════════════════════════
#  Shared primitives
# ═══════════════════════════════════════════════════════════════

@dataclass
class Relationship:
    """A relationship / arrow between two entities."""
    source: str
    target: str
    label: str = ""
    arrow_type: str = "-->"  # -->, ..|>, *--, ..>, <|--, etc.

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Relationship":
        return Relationship(
            source=str(d.get("source", "")),
            target=str(d.get("target", "")),
            label=str(d.get("label", "")),
            arrow_type=str(d.get("arrow_type", "-->")),
        )


@dataclass
class Note:
    """A note attached to an element."""
    target: str       # element name/alias the note is attached to
    position: str     # right, left, top, bottom
    text: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Note":
        pos = str(d.get("position", "right")).lower()
        if pos not in ("right", "left", "top", "bottom"):
            pos = "right"
        return Note(
            target=str(d.get("target", "")),
            position=pos,
            text=str(d.get("text", "")),
        )


# ═══════════════════════════════════════════════════════════════
#  Class Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class FieldIR:
    name: str
    type: str = ""
    visibility: str = "+"  # +, -, #

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FieldIR":
        vis = str(d.get("visibility", "+"))
        if vis not in ("+", "-", "#", "~"):
            vis = "+"
        return FieldIR(
            name=str(d.get("name", "")),
            type=str(d.get("type", "")),
            visibility=vis,
        )


@dataclass
class MethodIR:
    name: str
    return_type: str = ""
    params: str = ""
    visibility: str = "+"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MethodIR":
        vis = str(d.get("visibility", "+"))
        if vis not in ("+", "-", "#", "~"):
            vis = "+"
        return MethodIR(
            name=str(d.get("name", "")),
            return_type=str(d.get("return_type", "")),
            params=str(d.get("params", "")),
            visibility=vis,
        )


@dataclass
class ClassIR:
    name: str
    stereotype: str = ""
    is_abstract: bool = False
    is_interface: bool = False
    fields: List[FieldIR] = field(default_factory=list)
    methods: List[MethodIR] = field(default_factory=list)
    package: str = ""  # grouping layer

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ClassIR":
        return ClassIR(
            name=str(d.get("name", "")),
            stereotype=str(d.get("stereotype", "")),
            is_abstract=bool(d.get("is_abstract", False)),
            is_interface=bool(d.get("is_interface", False)),
            fields=[FieldIR.from_dict(f) for f in d.get("fields", [])],
            methods=[MethodIR.from_dict(m) for m in d.get("methods", [])],
            package=str(d.get("package", "")),
        )


@dataclass
class ClassDiagramIR:
    title: str = ""
    classes: List[ClassIR] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ClassDiagramIR":
        return ClassDiagramIR(
            title=str(d.get("title", "")),
            classes=[ClassIR.from_dict(c) for c in d.get("classes", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Use Case Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class ActorIR:
    name: str
    alias: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActorIR":
        return ActorIR(
            name=str(d.get("name", "")),
            alias=str(d.get("alias", "")),
        )


@dataclass
class UseCaseIR:
    name: str
    alias: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "UseCaseIR":
        return UseCaseIR(
            name=str(d.get("name", "")),
            alias=str(d.get("alias", "")),
        )


@dataclass
class UseCaseDiagramIR:
    title: str = ""
    system_name: str = "System"
    actors: List[ActorIR] = field(default_factory=list)
    usecases: List[UseCaseIR] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "UseCaseDiagramIR":
        return UseCaseDiagramIR(
            title=str(d.get("title", "")),
            system_name=str(d.get("system_name", "System")),
            actors=[ActorIR.from_dict(a) for a in d.get("actors", [])],
            usecases=[UseCaseIR.from_dict(u) for u in d.get("usecases", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Sequence Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class ParticipantIR:
    name: str
    alias: str = ""
    stereotype: str = ""
    participant_type: str = "participant"  # participant, actor, database, entity

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ParticipantIR":
        ptype = str(d.get("participant_type", "participant")).lower()
        if ptype not in ("participant", "actor", "database", "entity", "boundary", "control", "collections"):
            ptype = "participant"
        return ParticipantIR(
            name=str(d.get("name", "")),
            alias=str(d.get("alias", "")),
            stereotype=str(d.get("stereotype", "")),
            participant_type=ptype,
        )


@dataclass
class MessageIR:
    sender: str
    receiver: str
    label: str
    is_return: bool = False       # dashed return arrow
    activate: bool = False        # activate receiver after this message
    deactivate: bool = False      # deactivate sender after return

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MessageIR":
        return MessageIR(
            sender=str(d.get("sender", "")),
            receiver=str(d.get("receiver", "")),
            label=str(d.get("label", "")),
            is_return=bool(d.get("is_return", False)),
            activate=bool(d.get("activate", False)),
            deactivate=bool(d.get("deactivate", False)),
        )


@dataclass
class GroupIR:
    """An alt/else/opt/loop block wrapping a sequence of messages."""
    group_type: str = "alt"       # alt, opt, loop, critical
    label: str = ""
    messages: List[MessageIR] = field(default_factory=list)
    else_label: str = ""
    else_messages: List[MessageIR] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GroupIR":
        gtype = str(d.get("group_type", "alt")).lower()
        if gtype not in ("alt", "opt", "loop", "critical", "group"):
            gtype = "alt"
        return GroupIR(
            group_type=gtype,
            label=str(d.get("label", "")),
            messages=[MessageIR.from_dict(m) for m in d.get("messages", [])],
            else_label=str(d.get("else_label", "")),
            else_messages=[MessageIR.from_dict(m) for m in d.get("else_messages", [])],
        )


@dataclass
class SequenceDiagramIR:
    title: str = ""
    participants: List[ParticipantIR] = field(default_factory=list)
    messages: List[MessageIR] = field(default_factory=list)
    groups: List[GroupIR] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SequenceDiagramIR":
        return SequenceDiagramIR(
            title=str(d.get("title", "")),
            participants=[ParticipantIR.from_dict(p) for p in d.get("participants", [])],
            messages=[MessageIR.from_dict(m) for m in d.get("messages", [])],
            groups=[GroupIR.from_dict(g) for g in d.get("groups", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Activity Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class ActivityStepIR:
    """A step in an activity diagram — can be action, decision, fork, or stop."""
    step_type: str = "action"     # action, decision, fork, join, stop
    label: str = ""
    swimlane: str = ""            # ""=no swimlane
    # For decisions:
    condition: str = ""
    yes_steps: List["ActivityStepIR"] = field(default_factory=list)
    no_steps: List["ActivityStepIR"] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActivityStepIR":
        stype = str(d.get("step_type", "action")).lower()
        if stype not in ("action", "decision", "fork", "join", "stop"):
            stype = "action"
        return ActivityStepIR(
            step_type=stype,
            label=str(d.get("label", "")),
            swimlane=str(d.get("swimlane", "")),
            condition=str(d.get("condition", "")),
            yes_steps=[ActivityStepIR.from_dict(s) for s in d.get("yes_steps", [])],
            no_steps=[ActivityStepIR.from_dict(s) for s in d.get("no_steps", [])],
        )


@dataclass
class ActivityDiagramIR:
    title: str = ""
    swimlanes: List[str] = field(default_factory=list)
    steps: List[ActivityStepIR] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActivityDiagramIR":
        return ActivityDiagramIR(
            title=str(d.get("title", "")),
            swimlanes=list(d.get("swimlanes", [])),
            steps=[ActivityStepIR.from_dict(s) for s in d.get("steps", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  State Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class StateIR:
    name: str
    display_name: str = ""
    entry_action: str = ""
    exit_action: str = ""
    do_action: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "StateIR":
        return StateIR(
            name=str(d.get("name", "")),
            display_name=str(d.get("display_name", "")),
            entry_action=str(d.get("entry_action", "")),
            exit_action=str(d.get("exit_action", "")),
            do_action=str(d.get("do_action", "")),
        )


@dataclass
class TransitionIR:
    source: str         # state name or "[*]"
    target: str         # state name or "[*]"
    label: str = ""
    guard: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TransitionIR":
        return TransitionIR(
            source=str(d.get("source", "")),
            target=str(d.get("target", "")),
            label=str(d.get("label", "")),
            guard=str(d.get("guard", "")),
        )


@dataclass
class StateDiagramIR:
    title: str = ""
    states: List[StateIR] = field(default_factory=list)
    transitions: List[TransitionIR] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "StateDiagramIR":
        return StateDiagramIR(
            title=str(d.get("title", "")),
            states=[StateIR.from_dict(s) for s in d.get("states", [])],
            transitions=[TransitionIR.from_dict(t) for t in d.get("transitions", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Component Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class ComponentIR:
    name: str
    stereotype: str = ""
    package: str = ""     # grouping

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ComponentIR":
        return ComponentIR(
            name=str(d.get("name", "")),
            stereotype=str(d.get("stereotype", "")),
            package=str(d.get("package", "")),
        )


@dataclass
class InterfaceIR:
    name: str
    alias: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "InterfaceIR":
        return InterfaceIR(
            name=str(d.get("name", "")),
            alias=str(d.get("alias", "")),
        )


@dataclass
class ComponentDiagramIR:
    title: str = ""
    components: List[ComponentIR] = field(default_factory=list)
    interfaces: List[InterfaceIR] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ComponentDiagramIR":
        return ComponentDiagramIR(
            title=str(d.get("title", "")),
            components=[ComponentIR.from_dict(c) for c in d.get("components", [])],
            interfaces=[InterfaceIR.from_dict(i) for i in d.get("interfaces", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Package Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class PackageIR:
    name: str
    classes: List[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PackageIR":
        return PackageIR(
            name=str(d.get("name", "")),
            classes=list(d.get("classes", [])),
        )


@dataclass
class PackageDiagramIR:
    title: str = ""
    packages: List[PackageIR] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PackageDiagramIR":
        return PackageDiagramIR(
            title=str(d.get("title", "")),
            packages=[PackageIR.from_dict(p) for p in d.get("packages", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Deployment Diagram IR
# ═══════════════════════════════════════════════════════════════

@dataclass
class DeploymentNodeIR:
    name: str
    node_type: str = "node"  # node, database, cloud, artifact
    children: List[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DeploymentNodeIR":
        ntype = str(d.get("node_type", "node")).lower()
        if ntype not in ("node", "database", "cloud", "artifact"):
            ntype = "node"
        return DeploymentNodeIR(
            name=str(d.get("name", "")),
            node_type=ntype,
            children=list(d.get("children", [])),
        )


@dataclass
class DeploymentDiagramIR:
    title: str = ""
    nodes: List[DeploymentNodeIR] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DeploymentDiagramIR":
        return DeploymentDiagramIR(
            title=str(d.get("title", "")),
            nodes=[DeploymentNodeIR.from_dict(n) for n in d.get("nodes", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Navigation Diagram IR  (uses state diagram semantics)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ScreenIR:
    name: str
    display_name: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ScreenIR":
        return ScreenIR(
            name=str(d.get("name", "")),
            display_name=str(d.get("display_name", "")),
        )


@dataclass
class NavigationDiagramIR:
    title: str = ""
    screens: List[ScreenIR] = field(default_factory=list)
    transitions: List[TransitionIR] = field(default_factory=list)
    entry_screen: str = ""        # name of the launcher screen
    exit_screens: List[str] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NavigationDiagramIR":
        return NavigationDiagramIR(
            title=str(d.get("title", "")),
            screens=[ScreenIR.from_dict(s) for s in d.get("screens", [])],
            transitions=[TransitionIR.from_dict(t) for t in d.get("transitions", [])],
            entry_screen=str(d.get("entry_screen", "")),
            exit_screens=list(d.get("exit_screens", [])),
            notes=[Note.from_dict(n) for n in d.get("notes", [])],
        )


# ═══════════════════════════════════════════════════════════════
#  Registry: diagram_type → IR class
# ═══════════════════════════════════════════════════════════════

IR_CLASSES = {
    "class_diagram": ClassDiagramIR,
    "usecase_diagram": UseCaseDiagramIR,
    "sequence_diagram": SequenceDiagramIR,
    "activity_diagram": ActivityDiagramIR,
    "state_diagram": StateDiagramIR,
    "component_diagram": ComponentDiagramIR,
    "package_diagram": PackageDiagramIR,
    "deployment_diagram": DeploymentDiagramIR,
    "navigation_diagram": NavigationDiagramIR,
}


def parse_ir(diagram_type: str, data: Dict[str, Any]):
    """Parse a raw dict into the appropriate IR dataclass."""
    cls = IR_CLASSES.get(diagram_type)
    if cls is None:
        raise ValueError(f"Unknown diagram type: {diagram_type}")
    return cls.from_dict(data)
