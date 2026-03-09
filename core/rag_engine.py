"""
RAG Engine — the central orchestrator.

Workflow:
    1.  index_project(path)  → scan → parse → chunk → embed → store
    2.  query(question, …)   → embed query → retrieve top-K → build prompt → generate
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
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
_project_fingerprint: Optional[str] = None


def get_parsed_files() -> List[Dict]:
    return _parsed_files


def get_chunks() -> List[CodeChunk]:
    return _chunks


def get_project_path() -> Optional[str]:
    return _project_path


# ── Fingerprinting (skip re-indexing unchanged projects) ───────

def _compute_fingerprint(file_list: List[Dict]) -> str:
    """Hash of file paths + sizes to detect project changes."""
    h = hashlib.md5()
    for f in sorted(file_list, key=lambda x: x["path"]):
        h.update(f"{f['path']}:{f['size']}".encode())
    return h.hexdigest()


# ── Indexing ───────────────────────────────────────────────────

def index_project(project_path: str,
                  progress: Optional[Callable] = None,
                  force: bool = False) -> Dict:
    """
    Full indexing pipeline:
      scan files → parse → chunk → embed → store in ChromaDB.

    Skips re-indexing if the project hasn't changed (same files and sizes)
    unless *force* is True.

    Returns summary stats.
    """
    global _parsed_files, _chunks, _project_path, _project_fingerprint
    _project_path = project_path

    # 1. Scan
    if progress:
        progress("Scanning project files…")
    file_list = scan_project_files(project_path)

    # 1b. Check fingerprint — skip if unchanged
    new_fp = _compute_fingerprint(file_list)
    if not force and new_fp == _project_fingerprint and _chunks:
        if progress:
            progress("⚡ Project unchanged — using cached index.")
        return {
            "files": len(file_list),
            "parsed": len(_parsed_files),
            "chunks": len(_chunks),
            "indexed": True,
            "cached": True,
        }

    # 2. Parse (parallel — I/O-bound file reads + CPU regex)
    if progress:
        progress(f"Parsing {len(file_list)} files…")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda fi: parser.parse_file(fi["path"]),
                                file_list))
    _parsed_files = [pf for pf in results if pf]

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

    # 6. Save fingerprint for future skip-check
    _project_fingerprint = new_fp

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
    
    # ── Multi-Model Routing ──
    target_model = getattr(config, "MODEL_ROUTING", {}).get(analysis_type, config.LLM_MODEL)
    prompt = _build_prompt(question, context_blocks, analysis_type, target_model)
    
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

    # ── Multi-Model Routing ──
    target_model = getattr(config, "MODEL_ROUTING", {}).get(analysis_type, config.LLM_MODEL)
    prompt = _build_prompt(question, context_blocks, analysis_type, target_model)
    print(f"\n[LLM Router] Routing stream '{analysis_type}' task to model: {target_model}")

    return generate_stream(prompt, model=target_model)


# ── Prompt engineering ─────────────────────────────────────────

def _system_context(model_name: str = "AI Assistant") -> str:
    """Build model-aware system context string."""
    return (
        f"You are {model_name}, an expert AI assistant specialized in Android "
        "code analysis and software architecture. You have been given RELEVANT "
        "EXCERPTS from the project's codebase via a retrieval system. "
        "Use ONLY the provided context to answer. Be specific and reference "
        "actual class/method names from the context.\n"
    )

_ANALYSIS_INSTRUCTIONS = {
    "general": "Answer the question based on the code context provided.",
    "class_diagram": (
        "Generate a CLEAN, READABLE PlantUML class diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Identify the most important classes, "
        "their fields, methods, and how they relate to each other.\n\n"
        "RULES:\n"
        "- Add a title: title \"Class Diagram — [ProjectName]\"\n"
        "- Show only 4-6 MOST IMPORTANT classes (core domain, not helpers/utilities)\n"
        "- For each class show ONLY: 2-3 key fields, 2-4 public methods (skip getters/setters/toString)\n"
        "- Use visibility: + public, # protected, - private\n"
        "- Add <<stereotype>> on every class: <<Activity>>, <<ViewModel>>, <<Repository>>, <<Entity>>, <<Service>>\n"
        "- Group classes inside 'package \"LayerName\" { }' blocks (e.g. UI, Domain, Data)\n"
        "- LABEL EVERY relationship arrow with a verb: User --> Course : enrollsIn\n"
        "- Show multiplicity: User \"1\" *-- \"0..*\" Course\n"
        "- Use correct arrow types: inheritance --|>, implementation ..|>, composition *--, dependency ..>\n"
        "- For inheritance: 'class Child extends Parent' (NOT colon syntax)\n"
        "- Add 'note right of ClassName : Design Pattern' for any pattern used\n\n"
        "ANTI-DUPLICATION: Define each class EXACTLY ONCE. Never repeat a class declaration.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Include more than 6 classes — focus on clarity.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "sequence_diagram": (
        "Generate a CLEAN, READABLE PlantUML sequence diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Trace ONE complete user interaction "
        "flow from start to finish.\n\n"
        "GOAL: Show ONE clear user interaction flow that someone can follow step-by-step.\n\n"
        "RULES:\n"
        "- Add a title: title \"Sequence — [Flow Name]\"\n"
        "- Use at most 4-5 participants (not more)\n"
        "- Declare participants with stereotypes: participant \"ClassName\" as C1 <<Activity>>\n"
        "- Number each message for readability: C1 -> C2 : 1. loginUser(email, pwd)\n"
        "- Use activate/deactivate for lifeline bars\n"
        "- Use return arrows (dashed): C2 --> C1 : User object\n"
        "- Use alt/else for ONE key decision point, opt for optional behavior\n"
        "- Add 'note right : ...' explaining WHY, not what\n"
        "- Show ONE complete request-response round-trip end to end\n\n"
        "ANTI-DUPLICATION: Declare each participant EXACTLY ONCE. Never repeat a participant declaration.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Use more than 5 participants — keep it focused.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "activity_diagram": (
        "Generate a CLEAN, READABLE PlantUML activity diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Identify the primary user journey "
        "including decision points and key actions.\n\n"
        "GOAL: Show ONE primary user flow so someone can understand the app's navigation.\n\n"
        "RULES:\n"
        "- Add a title: title \"Activity Flow — [Flow Name]\"\n"
        "- Use start and stop nodes\n"
        "- Use 2-3 swimlanes max: |User|, |App|, |Backend|\n"
        "- Use activity syntax: :Action description;\n"
        "- Use decision diamonds: if (condition?) then (yes) ... else (no) ... endif\n"
        "- Use fork/join only if there's actual parallel behavior\n"
        "- Add 'note right : ...' for important business rules\n"
        "- Keep the total flow to 8-12 steps max\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Show more than one flow — pick the most important one.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
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
        "Generate a CLEAN, READABLE PlantUML state diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Identify lifecycle states, "
        "transitions, and callback methods.\n\n"
        "GOAL: Show the lifecycle of ONE key component so someone understands its states at a glance.\n\n"
        "RULES:\n"
        "- Add a title: title \"State Diagram — [ComponentName]\"\n"
        "- Limit to 5-7 states maximum\n"
        "- Define states with descriptions: state \"Displayed Name\" as S1\n"
        "- Add entry/do/exit actions inside states:\n"
        "  state S1 {\n"
        "    S1 : entry / initializeData()\n"
        "    S1 : exit / cleanup()\n"
        "  }\n"
        "- LABEL EVERY transition with event and guard: S1 --> S2 : onResume [dataReady]\n"
        "- Use [*] for initial and final states\n"
        "- Add 'note right of S1 : ...' for lifecycle callback explanations\n\n"
        "ANTI-DUPLICATION: Define each state EXACTLY ONCE. Never repeat a state declaration.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Show more than 7 states — keep it understandable.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "component_diagram": (
        "Generate a CLEAN, READABLE PlantUML component diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Identify major feature areas "
        "and how components within them communicate.\n\n"
        "GOAL: Show how the app's major components connect so someone understands the architecture.\n\n"
        "RULES:\n"
        "- Add a title: title \"Component Diagram — [ProjectName]\"\n"
        "- Group components into 2-4 feature packages\n"
        "- Use [ComponentName] shorthand: [LoginActivity], [UserRepository]\n"
        "- Add <<stereotype>> on each: <<Activity>>, <<Service>>, <<Repository>>\n"
        "- LABEL EVERY connection with interaction type: [Login] --> [AuthRepo] : validates credentials\n"
        "- Limit to 6-10 components total\n"
        "- Define interfaces if key contracts exist: interface \"AuthService\" as I1\n\n"
        "ANTI-DUPLICATION: Define each component EXACTLY ONCE. Never repeat a component declaration.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Include more than 10 components — group similar ones.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "usecase_diagram": (
        "Generate a CLEAN, READABLE PlantUML use case diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Identify actual app features "
        "that map to user-facing capabilities.\n\n"
        "GOAL: Show what the app lets users do, so someone understands its features at a glance.\n\n"
        "RULES:\n"
        "- Add a title: title \"Use Cases — [AppName]\"\n"
        "- Use 'left to right direction' for better layout\n"
        "- Define 1-2 actors: actor \"User\" as U\n"
        "- Wrap ALL use cases inside a rectangle: rectangle \"AppName\" { }\n"
        "- Define EACH use case EXACTLY ONCE with an alias: usecase \"Login\" as UC1\n"
        "- Use ONLY the aliases in relationships:\n"
        "  U --> UC1\n"
        "  UC1 ..> UC5 : <<include>>\n"
        "- NEVER use parentheses in relationships when using aliases\n"
        "- Show at least one <<include>> and one <<extend>>\n"
        "- Add 'note right of UC1 : brief description' for key use cases\n\n"
        "CRITICAL ANTI-DUPLICATION RULE:\n"
        "- Define each use case ONLY ONCE inside the rectangle block\n"
        "- Do NOT declare use cases both inside and outside the rectangle\n"
        "- Do NOT declare standalone use cases that duplicate ones in the rectangle\n"
        "- Each actor should be defined EXACTLY ONCE\n\n"
        "EXAMPLE OUTPUT:\n"
        "  @startuml\n"
        "  title \"Use Cases — MyApp\"\n"
        "  left to right direction\n"
        "  actor \"Student\" as U\n"
        "  rectangle \"MyApp\" {\n"
        "    usecase \"Login\" as UC1\n"
        "    usecase \"Browse Courses\" as UC2\n"
        "    usecase \"Take Quiz\" as UC3\n"
        "    usecase \"View Profile\" as UC4\n"
        "    usecase \"Authenticate\" as UC5\n"
        "  }\n"
        "  U --> UC1\n"
        "  U --> UC2\n"
        "  U --> UC3\n"
        "  U --> UC4\n"
        "  UC1 ..> UC5 : <<include>>\n"
        "  UC3 ..> UC2 : <<extend>>\n"
        "  note right of UC3 : Earns XP on completion\n"
        "  @enduml\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Include more than 7 use cases — focus on the core features.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "package_diagram": (
        "Generate a CLEAN, READABLE PlantUML package diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Map classes to their "
        "architectural layers and identify cross-layer dependencies.\n\n"
        "GOAL: Show the project's layer architecture so someone understands the code organization.\n\n"
        "RULES:\n"
        "- Add a title: title \"Package Diagram — [ProjectName]\"\n"
        "- Show 3-4 architectural layer packages\n"
        "- List 2-3 key classes inside each package\n"
        "- LABEL EVERY dependency arrow: ui ..> domain : calls\n"
        "- If a dependency violates clean architecture, add: note on link : Warning\n\n"
        "ANTI-DUPLICATION: Define each package and class EXACTLY ONCE. Never repeat.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: List more than 3 classes per package — show only the most important.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "deployment_diagram": (
        "Generate a CLEAN, READABLE PlantUML deployment diagram from the code context.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Identify devices, servers, "
        "services, and network protocols used.\n\n"
        "GOAL: Show where the app runs and what external services it connects to.\n\n"
        "RULES:\n"
        "- Add a title: title \"Deployment Diagram — [AppName]\"\n"
        "- Use nested nodes for the device: node \"Android Device\" { }\n"
        "- Use proper shapes: database for DB, cloud for services, node for servers\n"
        "- LABEL EVERY connection with protocol: app --> firebase : HTTPS (Retrofit)\n"
        "- Limit to 4-6 nodes total\n"
        "- Add 'note right of NodeName : ...' for purpose description\n\n"
        "ANTI-DUPLICATION: Define each node, database, and cloud EXACTLY ONCE.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Show more than 6 nodes — keep the layout clean.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
    ),
    "navigation_diagram": (
        "Generate a CLEAN, READABLE PlantUML state diagram that serves as a NAVIGATION MAP for this app.\n\n"
        "BEFORE GENERATING: Carefully read ALL code context. Find every Activity and Fragment, "
        "and trace how users navigate between them.\n\n"
        "GOAL: Show every screen and how the user moves between them, including app entry and exit points.\n\n"
        "RULES:\n"
        "- Add a title: title \"Navigation Map — [AppName]\"\n"
        "- Use state nodes for each screen: state \"ScreenName\" as S1\n"
        "- Use [*] for the app ENTRY point (launcher Activity) and EXIT points (back/finish)\n"
        "- LABEL EVERY transition with the USER ACTION that triggers it:\n"
        "  S1 --> S2 : taps \"Start Course\"\n"
        "  S3 --> [*] : presses Back\n"
        "- Show 5-10 screens max — only real Activity/Fragment classes from the code\n"
        "- Group related screens if needed using composite states\n"
        "- Add 'note right of S1 : ...' OUTSIDE state blocks for important entry conditions\n"
        "- NEVER put note directives inside state { } blocks\n"
        "- Show both forward navigation AND back navigation\n"
        "- Do NOT use state { } blocks unless nesting sub-states — simple states need no braces\n\n"
        "ANTI-DUPLICATION: Define each state/screen EXACTLY ONCE. Never repeat a state declaration.\n\n"
        "DO NOT: Include any explanation text outside @startuml/@enduml.\n"
        "DO NOT: Invent screens — only use Activity/Fragment classes found in the code.\n"
        "DO NOT: Include any skinparam or styling — styling is handled automatically.\n"
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


def _build_prompt(question: str, context: str, analysis_type: str,
                  model_name: str = "AI Assistant") -> str:
    instructions = _ANALYSIS_INSTRUCTIONS.get(
        analysis_type,
        _ANALYSIS_INSTRUCTIONS["general"],
    )
    return (
        f"{_system_context(model_name)}\n"
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
