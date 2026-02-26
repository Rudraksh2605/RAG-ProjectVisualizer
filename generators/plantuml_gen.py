"""
PlantUML diagram generators — class, sequence, activity, state-machine,
component, use-case, package, and deployment diagrams.

All generators use RAG to retrieve relevant code chunks before asking
the LLM to produce PlantUML syntax.
"""

from core import rag_engine


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
        f"Generate a PlantUML class diagram for the class '{focus_class}' "
        f"showing its fields, methods, inheritance, and relationships "
        f"with other classes."
        if focus_class
        else "Generate a PlantUML class diagram showing the main classes "
             "in this project with their relationships, inheritance, "
             "and key methods."
    )
    raw = rag_engine.query(question, analysis_type="class_diagram", top_k=10)
    return _extract_plantuml(raw)


def generate_sequence_diagram(focus: str = None) -> str:
    """
    Generate a PlantUML sequence diagram.
    """
    question = (
        f"Generate a PlantUML sequence diagram showing how '{focus}' "
        f"interacts with other classes through method calls."
        if focus
        else "Generate a PlantUML sequence diagram showing the main "
             "interactions between the UI, business logic, and data layers."
    )
    raw = rag_engine.query(question, analysis_type="sequence_diagram", top_k=10)
    return _extract_plantuml(raw)


def generate_activity_diagram() -> str:
    """
    Generate a PlantUML activity diagram showing navigation flows.
    """
    question = (
        "Generate a PlantUML activity diagram showing all screen navigation "
        "flows in this Android app. Include conditional branches, user "
        "decisions, and swimlanes for different user journeys."
    )
    raw = rag_engine.query(
        question, analysis_type="activity_diagram",
        top_k=12, layer_filter="UI",
    )
    return _extract_plantuml(raw)


# ═══════════════════════════════════════════════════════════════
#  New diagram generators
# ═══════════════════════════════════════════════════════════════

def generate_state_diagram(focus_class: str = None) -> str:
    """
    Generate a PlantUML state diagram showing lifecycle states
    and transitions for an Android component or business object.
    """
    question = (
        f"Generate a PlantUML state diagram for the class '{focus_class}' "
        f"showing all possible states, state transitions, triggers, "
        f"and lifecycle callback methods (e.g. onCreate, onResume, onPause, "
        f"onDestroy). Include guard conditions where applicable."
        if focus_class
        else "Generate a PlantUML state diagram showing the lifecycle states "
             "of the main Activity or Fragment in this project, including "
             "all state transitions and lifecycle callbacks."
    )
    raw = rag_engine.query(question, analysis_type="state_diagram", top_k=10)
    return _extract_plantuml(raw)


def generate_component_diagram() -> str:
    """
    Generate a PlantUML component diagram showing Android Manifest
    components and their interactions via Intents.
    """
    question = (
        "Generate a PlantUML component diagram showing all Android Manifest "
        "components in this project: Activities, Services, BroadcastReceivers, "
        "and ContentProviders. Show how they interact through Intents, "
        "bound services, and content URIs. Group components by their "
        "functional area."
    )
    raw = rag_engine.query(question, analysis_type="component_diagram", top_k=12)
    return _extract_plantuml(raw)


def generate_usecase_diagram() -> str:
    """
    Generate a PlantUML use-case diagram showing actor–system interactions
    extracted from the UI and ViewModel layers.
    """
    question = (
        "Generate a PlantUML use case diagram for this Android app. "
        "Identify the primary actors (User, Admin, External System) and "
        "all use cases by analyzing the UI Activities/Fragments, ViewModels, "
        "and public API methods. Group related use cases together and show "
        "include/extend relationships where applicable."
    )
    raw = rag_engine.query(question, analysis_type="usecase_diagram", top_k=12)
    return _extract_plantuml(raw)


def generate_package_diagram() -> str:
    """
    Generate a PlantUML package diagram showing the package hierarchy
    and inter-layer dependencies (UI → Domain → Data).
    """
    question = (
        "Generate a PlantUML package diagram showing the package structure "
        "of this Android project. Group classes into logical packages and "
        "architectural layers (UI/Presentation, Domain/Business Logic, "
        "Data/Repository). Draw directional dependency arrows between "
        "packages to show which layer depends on which. Highlight any "
        "dependency rule violations (e.g. Data layer depending on UI)."
    )
    raw = rag_engine.query(question, analysis_type="package_diagram", top_k=12)
    return _extract_plantuml(raw)


def generate_deployment_diagram() -> str:
    """
    Generate a PlantUML deployment diagram showing the app's external
    connections: REST APIs, databases, Firebase, third-party SDKs.
    """
    question = (
        "Generate a PlantUML deployment diagram for this Android app. "
        "Show the mobile device node containing the app, and all external "
        "nodes it connects to: REST API servers (from Retrofit/OkHttp), "
        "databases (Room/SQLite), cloud services (Firebase, etc.), and "
        "third-party SDKs. Label each connection with the protocol or "
        "library used (HTTP, gRPC, ContentProvider, etc.)."
    )
    raw = rag_engine.query(question, analysis_type="deployment_diagram", top_k=12)
    return _extract_plantuml(raw)


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
#  PlantUML extraction helper
# ═══════════════════════════════════════════════════════════════

def _extract_plantuml(text: str) -> str:
    """
    Extract the PlantUML block from LLM output.
    If the model wrapped it in @startuml/@enduml — great.
    If not, wrap the whole output.
    """
    if "@startuml" in text and "@enduml" in text:
        start = text.index("@startuml")
        end = text.index("@enduml") + len("@enduml")
        return text[start:end]

    # Try to extract from ```plantuml code fences
    if "```plantuml" in text:
        start = text.index("```plantuml") + len("```plantuml")
        end = text.index("```", start)
        body = text[start:end].strip()
        return f"@startuml\n{body}\n@enduml"

    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            body = parts[1].strip()
            if body.startswith("plantuml"):
                body = body[len("plantuml"):].strip()
            return f"@startuml\n{body}\n@enduml"

    # Fallback: wrap entire output
    return f"@startuml\n{text.strip()}\n@enduml"
