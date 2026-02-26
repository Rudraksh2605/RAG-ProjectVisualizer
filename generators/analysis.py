"""
Project analysis utilities — deterministic stats and
AI-enhanced complexity analysis.
"""

from typing import Dict, List
from core import rag_engine


def get_overview(stats: Dict) -> Dict:
    """
    Build a dashboard-ready overview from project stats.
    """
    return {
        "total_files": stats.get("total_files", 0),
        "total_chunks": stats.get("total_chunks", 0),
        "java_files": stats.get("java_files", 0),
        "kotlin_files": stats.get("kotlin_files", 0),
        "xml_files": stats.get("xml_files", 0),
        "gradle_files": stats.get("gradle_files", 0),
        "total_classes": len(stats.get("classes", [])),
        "components_by_type": stats.get("components_by_type", {}),
        "components_by_layer": stats.get("components_by_layer", {}),
    }


def detect_architecture_pattern(stats: Dict) -> str:
    """Heuristic architecture pattern detection from class types."""
    types = stats.get("components_by_type", {})
    has_viewmodel = types.get("ViewModel", 0) > 0
    has_repository = types.get("Repository", 0) > 0
    has_dao = types.get("DAO", 0) > 0
    has_activity = types.get("Activity", 0) > 0
    has_fragment = types.get("Fragment", 0) > 0

    if has_viewmodel and has_repository:
        return "MVVM (Model-View-ViewModel)"
    if has_viewmodel:
        return "MVVM (ViewModel detected, no Repository layer)"
    if has_activity and has_dao and not has_viewmodel:
        return "MVC (Activities directly accessing DAOs)"
    if has_activity or has_fragment:
        return "Activity/Fragment based (no clear pattern)"
    return "Unknown"


def analyze_complexity_ai() -> str:
    """Use RAG to provide AI-enhanced complexity analysis."""
    question = (
        "Analyze the computational complexity of the most important methods. "
        "Identify potential performance bottlenecks and suggest optimizations."
    )
    return rag_engine.query(question, analysis_type="complexity", top_k=10)


def get_class_list(stats: Dict) -> List[str]:
    """Return sorted list of class names."""
    return sorted(cls["name"] for cls in stats.get("classes", []))


def get_manifest_info() -> Dict:
    """Extract manifest information from parsed files."""
    for pf in rag_engine.get_parsed_files():
        if pf.get("type") == "manifest":
            return {
                "package": pf.get("package", "N/A"),
                "activities": pf.get("activities", []),
                "services": pf.get("services", []),
                "receivers": pf.get("receivers", []),
                "permissions": pf.get("permissions", []),
                "min_sdk": pf.get("min_sdk", "N/A"),
                "target_sdk": pf.get("target_sdk", "N/A"),
            }
    return {}


def get_gradle_info() -> Dict:
    """Extract Gradle build info from parsed files."""
    for pf in rag_engine.get_parsed_files():
        if pf.get("type") == "gradle":
            return {
                "dependencies": pf.get("dependencies", []),
                "plugins": pf.get("plugins", []),
                "min_sdk": pf.get("min_sdk", "N/A"),
                "compile_sdk": pf.get("compile_sdk", "N/A"),
            }
    return {}
