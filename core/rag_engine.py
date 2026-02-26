"""
RAG Engine — the central orchestrator.

Workflow:
    1.  index_project(path)  → scan → parse → chunk → embed → store
    2.  query(question, …)   → embed query → retrieve top-K → build prompt → generate
"""

from typing import List, Dict, Optional, Callable
from core import parser, embeddings, vector_store
from core.chunker import chunk_parsed_files, CodeChunk
from core.ollama_client import generate, generate_stream
from utils.helpers import scan_project_files
import config


# ── Project-level cache ────────────────────────────────────────
_parsed_files: List[Dict] = []
_chunks: List[CodeChunk] = []
_project_path: Optional[str] = None


def get_parsed_files() -> List[Dict]:
    return _parsed_files


def get_chunks() -> List[CodeChunk]:
    return _chunks


def get_project_path() -> Optional[str]:
    return _project_path


# ── Indexing ───────────────────────────────────────────────────

def index_project(project_path: str,
                  progress: Optional[Callable] = None) -> Dict:
    """
    Full indexing pipeline:
      scan files → parse → chunk → embed → store in ChromaDB.

    Returns summary stats.
    """
    global _parsed_files, _chunks, _project_path
    _project_path = project_path

    # 1. Scan
    if progress:
        progress("Scanning project files…")
    file_list = scan_project_files(project_path)

    # 2. Parse
    if progress:
        progress(f"Parsing {len(file_list)} files…")
    _parsed_files = []
    for fi in file_list:
        pf = parser.parse_file(fi["path"])
        if pf:
            _parsed_files.append(pf)

    # 3. Chunk
    if progress:
        progress("Chunking into semantic units…")
    _chunks = chunk_parsed_files(_parsed_files)

    if not _chunks:
        return {"files": len(file_list), "parsed": len(_parsed_files),
                "chunks": 0, "indexed": False}

    # 4. Embed
    if progress:
        progress(f"Embedding {len(_chunks)} chunks (this may take a moment)…")

    def _emb_progress(done, total):
        if progress:
            progress(f"Embedding chunks: {done}/{total}")

    emb_vectors = embeddings.embed_batch(
        [c.content for c in _chunks], progress_callback=_emb_progress
    )

    # 5. Store
    if progress:
        progress("Storing in vector database…")
    vector_store.reset_collection()
    vector_store.upsert_chunks(_chunks, emb_vectors)

    stats = {
        "files": len(file_list),
        "parsed": len(_parsed_files),
        "chunks": len(_chunks),
        "indexed": True,
    }
    if progress:
        progress(f"✅ Indexed {stats['chunks']} chunks from {stats['parsed']} files.")
    return stats


# ── Retrieval + Generation ─────────────────────────────────────

def query(question: str,
          analysis_type: str = "general",
          top_k: int = None,
          layer_filter: str = None,
          type_filter: str = None) -> str:
    """
    End-to-end RAG query:
      embed question → retrieve → build prompt → generate answer.
    """
    # Embed the question
    q_emb = embeddings.embed_text(question)

    # Build optional metadata filter
    where = {}
    if layer_filter:
        where["layer"] = layer_filter
    if type_filter:
        where["component_type"] = type_filter

    results = vector_store.search(
        q_emb,
        top_k=top_k or config.RAG_TOP_K,
        where=where if where else None,
    )

    context_blocks = _format_retrieved_context(results)
    prompt = _build_prompt(question, context_blocks, analysis_type)
    
    # ── Multi-Model Routing ──
    # Pick the best model for this specific task
    target_model = getattr(config, "MODEL_ROUTING", {}).get(analysis_type, config.LLM_MODEL)
    print(f"\n[LLM Router] Routing '{analysis_type}' task to model: {target_model}")
    
    return generate(prompt, model=target_model)


def query_stream(question: str,
                 analysis_type: str = "general",
                 top_k: int = None,
                 layer_filter: str = None,
                 type_filter: str = None):
    """
    Streaming version — yields tokens for the Streamlit chat UI.
    """
    q_emb = embeddings.embed_text(question)

    where = {}
    if layer_filter:
        where["layer"] = layer_filter
    if type_filter:
        where["component_type"] = type_filter

    results = vector_store.search(
        q_emb,
        top_k=top_k or config.RAG_TOP_K,
        where=where if where else None,
    )

    context_blocks = _format_retrieved_context(results)
    prompt = _build_prompt(question, context_blocks, analysis_type)

    # ── Multi-Model Routing ──
    target_model = getattr(config, "MODEL_ROUTING", {}).get(analysis_type, config.LLM_MODEL)
    print(f"\n[LLM Router] Routing stream '{analysis_type}' task to model: {target_model}")

    return generate_stream(prompt, model=target_model)


# ── Prompt engineering ─────────────────────────────────────────

_SYSTEM_CONTEXT = (
    "You are DeepSeek-Coder, an expert AI assistant specialized in Android "
    "code analysis and software architecture. You have been given RELEVANT "
    "EXCERPTS from the project's codebase via a retrieval system. "
    "Use ONLY the provided context to answer. Be specific and reference "
    "actual class/method names from the context.\n"
)

_ANALYSIS_INSTRUCTIONS = {
    "general": "Answer the question based on the code context provided.",
    "class_diagram": (
        "Generate a valid PlantUML class diagram from the code context. "
        "Include class names, key fields, method signatures, and relationships "
        "(inheritance, composition, dependency). Use proper PlantUML syntax. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    "sequence_diagram": (
        "Generate a valid PlantUML sequence diagram showing the interactions "
        "between the classes in the context. Focus on method call chains. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    "activity_diagram": (
        "Generate a valid PlantUML activity diagram showing navigation flows "
        "and user interactions in this Android app. Use swimlanes for "
        "different user journeys. Output ONLY the PlantUML code between "
        "@startuml and @enduml."
    ),
    "dependency_graph": (
        "Generate valid Graphviz DOT syntax showing the dependency graph "
        "of the classes in the context. Label edges with the relationship "
        "type (extends, implements, uses, injects). "
        "Output ONLY the DOT code between digraph { and the final }."
    ),
    "doc_overview": (
        "Write a project overview including: App Name, Purpose (one paragraph), "
        "Target Users, and Core Features (bullet list). Be specific using "
        "class and method names from the context."
    ),
    "doc_architecture": (
        "Describe the architecture pattern (MVVM/MVP/MVC). List the layers "
        "(Presentation, Business Logic, Data) with actual class names. "
        "Include a data flow description."
    ),
    "doc_features": (
        "List ALL features of this application with descriptions, grouped by "
        "category (Authentication, Main Features, Data Storage, Communication). "
        "Use actual method names to prove each feature exists."
    ),
    "doc_screens": (
        "List every Activity and Fragment with: Purpose, UI Elements, and "
        "Navigation targets. Include actual class names."
    ),
    "doc_tech_stack": (
        "List the complete technology stack: Language, Android Components, "
        "Libraries (from Gradle dependencies), UI framework, networking, "
        "database, and DI framework."
    ),
    "doc_data_flow": (
        "Describe the data flow architecture: how data moves from API/DB "
        "to the UI. Include state management approach and concrete class names."
    ),
    "doc_api": (
        "List all API endpoints, network clients, and data models. "
        "If no external APIs, describe how data is fetched."
    ),
    "complexity": (
        "Analyze the complexity of the code. Identify the most complex methods, "
        "estimate time/space complexity, and suggest optimizations."
    ),
}


def _build_prompt(question: str, context: str, analysis_type: str) -> str:
    instructions = _ANALYSIS_INSTRUCTIONS.get(
        analysis_type,
        _ANALYSIS_INSTRUCTIONS["general"],
    )
    return (
        f"{_SYSTEM_CONTEXT}\n"
        f"TASK: {instructions}\n\n"
        f"RETRIEVED CODE CONTEXT:\n"
        f"{'=' * 60}\n"
        f"{context}\n"
        f"{'=' * 60}\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER:\n"
    )


def _format_retrieved_context(results: Dict) -> str:
    """Format ChromaDB search results into a readable context string."""
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    blocks = []
    for doc, meta in zip(docs, metas):
        header = (
            f"[{meta.get('chunk_type', '?')}] "
            f"{meta.get('component_name', '?')} "
            f"({meta.get('component_type', '?')}, Layer: {meta.get('layer', '?')})"
        )
        blocks.append(f"### {header}\n{doc}")

    return "\n\n---\n\n".join(blocks) if blocks else "(No relevant context found)"


# ── Project statistics (no AI needed) ──────────────────────────

def get_project_stats() -> Dict:
    """Return aggregate stats about the indexed project."""
    stats = {
        "total_files": len(_parsed_files),
        "total_chunks": len(_chunks),
        "java_files": 0,
        "kotlin_files": 0,
        "xml_files": 0,
        "gradle_files": 0,
        "classes": [],
        "components_by_type": {},
        "components_by_layer": {},
    }

    for pf in _parsed_files:
        lang = pf.get("language", pf.get("type", ""))
        if lang == "java":
            stats["java_files"] += 1
        elif lang == "kotlin":
            stats["kotlin_files"] += 1
        elif lang in ("layout", "manifest"):
            stats["xml_files"] += 1
        elif lang == "gradle":
            stats["gradle_files"] += 1

        for cls in pf.get("classes", []):
            stats["classes"].append(cls)
            ct = cls.get("component_type", "Class")
            stats["components_by_type"][ct] = stats["components_by_type"].get(ct, 0) + 1
            ly = cls.get("layer", "Other")
            stats["components_by_layer"][ly] = stats["components_by_layer"].get(ly, 0) + 1

    return stats
