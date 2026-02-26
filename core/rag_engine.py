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
    "state_diagram": (
        "Generate a valid PlantUML state diagram showing the lifecycle states "
        "and state transitions of the Android component or class in the context. "
        "Include lifecycle callbacks (onCreate, onResume, onPause, onDestroy), "
        "guard conditions, and entry/exit actions. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    "component_diagram": (
        "Generate a valid PlantUML component diagram showing the Android "
        "Manifest components (Activities, Services, BroadcastReceivers, "
        "ContentProviders) and their interactions via Intents, bound services, "
        "and content URIs. Group by functional area. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    "usecase_diagram": (
        "Generate a valid PlantUML use case diagram identifying the actors "
        "(User, Admin, External System) and all use cases based on the UI "
        "Activities, Fragments, ViewModels, and API methods in the context. "
        "Show include/extend relationships between use cases. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    "package_diagram": (
        "Generate a valid PlantUML package diagram showing the package "
        "structure grouped by architectural layers (Presentation, Domain, Data). "
        "Draw dependency arrows between packages. Highlight any dependency "
        "rule violations. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    "deployment_diagram": (
        "Generate a valid PlantUML deployment diagram showing the mobile "
        "device node with the app, and external nodes: REST API servers, "
        "databases (Room/SQLite), cloud services (Firebase), and third-party "
        "SDKs. Label connections with protocols and libraries used. "
        "Output ONLY the PlantUML code between @startuml and @enduml."
    ),
    # ── Security & Code Quality Scans ──────────────────────────
    "sec_hardcoded_secrets": (
        "You are a senior Android security auditor. Analyze the code context "
        "for hardcoded API keys, tokens, passwords, secret strings, and "
        "credentials. Check for strings that look like Base64-encoded secrets, "
        "OAuth tokens, Firebase keys, or AWS/GCP credentials embedded directly "
        "in Java/Kotlin source files instead of BuildConfig or local.properties. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_insecure_network": (
        "You are a senior Android security auditor. Analyze the code for "
        "insecure network communication: plain HTTP URLs (not HTTPS), disabled "
        "SSL certificate validation, missing certificate pinning, trusting all "
        "certificates via custom TrustManagers, cleartext traffic enabled in "
        "AndroidManifest, and insecure WebSocket connections. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_sql_injection": (
        "You are a senior Android security auditor. Analyze the code for SQL "
        "injection vulnerabilities: raw SQL queries using string concatenation, "
        "missing parameterized queries in Room/SQLite, unprotected or exported "
        "ContentProviders without proper permission checks, and dynamic query "
        "construction from user input. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_data_exposure": (
        "You are a senior Android security auditor. Analyze the code for "
        "sensitive data exposure: logging of passwords/tokens/PII via Log.d, "
        "storing sensitive data in unencrypted SharedPreferences, writing "
        "private data to external storage without encryption, exposing data "
        "through Intents without proper flags, and clipboard data leaks. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_permission_misuse": (
        "You are a senior Android security auditor. Analyze manifest and code "
        "for permission issues: dangerous permissions requested but never used, "
        "missing runtime permission checks for camera/location/storage, "
        "exported Activities/Services/Receivers without permission protection, "
        "and use of signature-level permissions incorrectly. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_memory_leaks": (
        "You are a senior Android code quality auditor. Analyze for memory leaks: "
        "static references to Activity/Context, inner classes holding Activity "
        "references, Handler/Runnable leaks, unclosed Cursor/InputStream/DB "
        "connections, views not nullified in onDestroyView, and AsyncTask or "
        "thread references surviving configuration changes. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_solid_violations": (
        "You are a senior software architect. Analyze the code for SOLID "
        "principle violations: God classes with too many responsibilities "
        "(Single Responsibility), concrete class dependencies instead of "
        "interfaces (Dependency Inversion), classes that must change for "
        "unrelated reasons (Open-Closed), large interfaces forcing unused "
        "implementations (Interface Segregation), and subclasses that break "
        "parent class contracts (Liskov Substitution). "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_android_antipatterns": (
        "You are a senior Android developer. Analyze the code for common "
        "Android anti-patterns: network/disk operations on the main thread, "
        "missing null safety checks, deprecated API usage, hardcoded strings "
        "and dimensions in layouts instead of resources, Context misuse "
        "(Application vs Activity), and Fragment instantiation with constructor "
        "arguments instead of newInstance pattern. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_error_handling": (
        "You are a senior Android developer. Analyze error handling quality: "
        "empty catch blocks that swallow exceptions, catching generic Exception "
        "instead of specific types, missing try-catch around IO/network/DB "
        "operations, missing null checks before method calls, and missing "
        "error states in UI (no error handling in Retrofit callbacks). "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
    ),
    "sec_performance": (
        "You are a senior Android performance engineer. Analyze for performance "
        "issues: unnecessary object allocation in loops or onDraw, missing view "
        "holder pattern in RecyclerView, nested layouts causing overdraw, "
        "synchronous operations blocking the UI thread, large bitmap loading "
        "without downsampling, and repeated database queries without caching. "
        "Return findings as a JSON array with keys: severity, title, location, "
        "description, recommendation. Output ONLY the JSON array."
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
