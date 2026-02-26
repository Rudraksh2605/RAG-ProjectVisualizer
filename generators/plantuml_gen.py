"""
PlantUML diagram generators — class, sequence, and activity diagrams.
All three use RAG to retrieve relevant code chunks before asking
DeepSeek Coder to produce PlantUML syntax.
"""

from core import rag_engine


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
