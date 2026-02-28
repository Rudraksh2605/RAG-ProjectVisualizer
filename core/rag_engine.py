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
        "Generate a valid, DETAILED PlantUML class diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Use visibility markers: + public, - private, # protected, ~ package-private\n"
        "- Show method return types: + getUserName() : String\n"
        "- Add <<stereotype>> annotations on classes: <<Activity>>, <<ViewModel>>, <<Repository>>, <<Entity>>, <<Singleton>>, <<Interface>>\n"
        "- Group related classes inside 'package \"LayerName\" { }' blocks\n"
        "- Show ALL relationships you can infer: inheritance (--|>), implementation (..|>), composition (*--), aggregation (o--), dependency (..>), association (-->)\n"
        "- Label relationship arrows with role names and multiplicity where applicable, e.g.: User \"1\" *-- \"0..*\" Order : places\n"
        "- Add 'note right of ClassName : ...' for important design patterns (Singleton, Observer, Factory etc.)\n"
        "- For inheritance use 'class Child extends Parent', NOT 'class Child : Parent' (colon syntax is INVALID)\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam classAttributeIconSize 0\n"
        "  skinparam classFontStyle bold\n"
        "  skinparam packageStyle rectangle\n"
        "  skinparam class {\n"
        "    BackgroundColor #1a1a2e\n"
        "    BorderColor #7c3aed\n"
        "    FontColor #e2e8f0\n"
        "    ArrowColor #06b6d4\n"
        "    StereotypeFontColor #a78bfa\n"
        "  }\n\n"
        "DO: Include at least 4-6 classes with their fields and methods.\n"
        "DO: Show at least 3 different relationship types.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
    ),
    "sequence_diagram": (
        "Generate a valid, DETAILED PlantUML sequence diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Declare participants with stereotypes: participant \"ClassName\" as C1 <<Activity>>\n"
        "- Use activate/deactivate for lifeline bars to show when objects are active\n"
        "- Show method call arguments where known: C1 -> C2 : fetchUser(userId)\n"
        "- Use return arrows (dashed): C2 --> C1 : User object\n"
        "- Use combined fragments for control flow:\n"
        "  * alt / else — conditional branches\n"
        "  * opt — optional execution\n"
        "  * loop — repeated calls\n"
        "  * ref — reference to another interaction\n"
        "- Add 'note right : ...' or 'note over C1,C2 : ...' for important logic steps\n"
        "- Group related messages using 'group \"Label\"' blocks\n"
        "- Show at least one complete request-response round-trip\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam sequenceArrowThickness 2\n"
        "  skinparam sequenceParticipantBorderColor #7c3aed\n"
        "  skinparam sequenceParticipantBackgroundColor #1a1a2e\n"
        "  skinparam sequenceParticipantFontColor #e2e8f0\n"
        "  skinparam sequenceLifeLineBorderColor #06b6d4\n"
        "  skinparam sequenceGroupBackgroundColor #2d2d44\n\n"
        "DO: Show at least 5-8 meaningful message exchanges.\n"
        "DO: Include at least one alt/opt/loop fragment.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
    ),
    "activity_diagram": (
        "Generate a valid, DETAILED PlantUML activity diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Use swimlanes with |Actor| or |Component| syntax to separate responsibilities\n"
        "- Use proper activity node syntax: :Action description; (colon + semicolon)\n"
        "- Use decision diamonds: if (condition?) then (yes) ... else (no) ... endif\n"
        "- Use fork/join for parallel flows: fork ... fork again ... end fork\n"
        "- Add 'note right : ...' for important business rules or side effects\n"
        "- Use start and stop nodes: start ... stop\n"
        "- Use (#color) for highlighting critical actions: :Critical Action;<<important>>\n"
        "- Show at least 2-3 complete user flow paths from start to end\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam ActivityDiamondBackgroundColor #7c3aed\n"
        "  skinparam ActivityDiamondFontColor #e2e8f0\n"
        "  skinparam ActivityBackgroundColor #1a1a2e\n"
        "  skinparam ActivityBorderColor #06b6d4\n"
        "  skinparam ActivityFontColor #e2e8f0\n"
        "  skinparam SwimlaneBackgroundColor #0f172a\n"
        "  skinparam SwimlaneBorderColor #334155\n\n"
        "DO: Include all major navigation flows and user decision points.\n"
        "DO: Use swimlanes to separate UI, business logic, and data layers.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
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
        "Generate a valid, DETAILED PlantUML state diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Define states with descriptions: state \"Displayed Name\" as S1\n"
        "- Add entry/do/exit actions inside states:\n"
        "  state S1 {\n"
        "    S1 : entry / initializeData()\n"
        "    S1 : do / listenForUpdates()\n"
        "    S1 : exit / cleanupResources()\n"
        "  }\n"
        "- Use composite (nested) states for complex lifecycles: state \"ParentState\" as PS { state \"Child1\" as C1 }\n"
        "- Show guard conditions on transitions: S1 --> S2 : onEvent [guardCondition]\n"
        "- Use [*] for initial and final states: [*] --> S1 and S_final --> [*]\n"
        "- Add 'note right of S1 : ...' for lifecycle callback explanations\n"
        "- Include Android lifecycle states: Created, Started, Resumed, Paused, Stopped, Destroyed\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam state {\n"
        "    BackgroundColor #1a1a2e\n"
        "    BorderColor #7c3aed\n"
        "    FontColor #e2e8f0\n"
        "    ArrowColor #06b6d4\n"
        "    StartColor #4ade80\n"
        "    EndColor #f87171\n"
        "  }\n\n"
        "DO: Show the complete lifecycle with at least 5-6 states and transitions.\n"
        "DO: Include guard conditions and actions on transitions.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
    ),
    "component_diagram": (
        "Generate a valid, DETAILED PlantUML component diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Declare components with stereotypes: component \"Name\" <<Activity>> as C1\n"
        "- Use [ComponentName] shorthand for simple components\n"
        "- Define interfaces: interface \"InterfaceName\" as I1\n"
        "- Show provided interfaces (lollipop): C1 --(  I1\n"
        "- Show required interfaces (socket): C2 )--  I1\n"
        "- Use package or rectangle blocks to group by functional area:\n"
        "  package \"Authentication\" {\n"
        "    [LoginActivity]\n"
        "    [AuthRepository]\n"
        "  }\n"
        "- Label connections with interaction type: C1 --> C2 : Intent\n"
        "- Show ports for external connections where applicable\n"
        "- Include ALL component types found: Activities, Services, BroadcastReceivers, ContentProviders, Repositories\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam component {\n"
        "    BackgroundColor #1a1a2e\n"
        "    BorderColor #7c3aed\n"
        "    FontColor #e2e8f0\n"
        "    ArrowColor #06b6d4\n"
        "    StereotypeFontColor #a78bfa\n"
        "  }\n"
        "  skinparam package {\n"
        "    BackgroundColor #0f172a\n"
        "    BorderColor #334155\n"
        "    FontColor #94a3b8\n"
        "  }\n\n"
        "DO: Show all manifest components and their interactions.\n"
        "DO: Group components by feature area.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
    ),
    "usecase_diagram": (
        "Generate a valid, DETAILED PlantUML use case diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Set layout direction: left to right direction\n"
        "- Define actors: actor \"User\" as U1\n"
        "- Define system boundary: rectangle \"App Name\" {\n"
        "- Define use cases with aliases: usecase \"Login\" as UC1\n"
        "- CRITICAL: Always wrap use case names in parentheses in relationships:\n"
        "  U1 --> (Login)      ✓ CORRECT\n"
        "  U1 --> Login         ✗ WRONG — will cause syntax error\n"
        "- Show <<include>> relationships: (View Profile) ..> (Authenticate) : <<include>>\n"
        "- Show <<extend>> relationships: (Reset Password) ..> (Login) : <<extend>>\n"
        "- Add 'note right of UC1 : ...' for use case descriptions\n"
        "- Group related use cases inside sub-rectangles if there are many\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  left to right direction\n"
        "  skinparam usecase {\n"
        "    BackgroundColor #1a1a2e\n"
        "    BorderColor #7c3aed\n"
        "    FontColor #e2e8f0\n"
        "    ArrowColor #06b6d4\n"
        "    StereotypeFontColor #a78bfa\n"
        "  }\n"
        "  skinparam actor {\n"
        "    BackgroundColor #1a1a2e\n"
        "    BorderColor #4ade80\n"
        "    FontColor #e2e8f0\n"
        "  }\n"
        "  skinparam rectangle {\n"
        "    BackgroundColor #0f172a\n"
        "    BorderColor #334155\n"
        "    FontColor #94a3b8\n"
        "  }\n\n"
        "DO: Include at least 5-8 use cases derived from the actual code.\n"
        "DO: Show at least one <<include>> and one <<extend>> relationship.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
    ),
    "package_diagram": (
        "Generate a valid, DETAILED PlantUML package diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Define packages with layer stereotypes and colors:\n"
        "  package \"ui\" <<Presentation>> #1a1a2e {\n"
        "    class LoginActivity\n"
        "    class MainFragment\n"
        "  }\n"
        "- Use different colors per architectural layer:\n"
        "  * Presentation/UI: #1e293b\n"
        "  * Domain/Business Logic: #1a1a2e\n"
        "  * Data/Repository: #0f172a\n"
        "- Draw directional dependency arrows: ui ..> domain : uses\n"
        "- Label arrows with relationship descriptions\n"
        "- If a dependency VIOLATES clean architecture rules (e.g. Data -> UI), mark it:\n"
        "  note on link : ⚠️ VIOLATION: Data layer should not depend on UI\n"
        "- List the actual classes inside each package (at least the most important ones)\n"
        "- Show sub-packages for deeper hierarchies when present\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam packageStyle rectangle\n"
        "  skinparam package {\n"
        "    BorderColor #7c3aed\n"
        "    FontColor #e2e8f0\n"
        "    StereotypeFontColor #a78bfa\n"
        "  }\n"
        "  skinparam arrow {\n"
        "    Color #06b6d4\n"
        "    FontColor #94a3b8\n"
        "  }\n\n"
        "DO: Show all major packages with their key classes listed inside.\n"
        "DO: Flag any dependency violations with notes.\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
    ),
    "deployment_diagram": (
        "Generate a valid, DETAILED PlantUML deployment diagram from the code context.\n\n"
        "STRUCTURAL REQUIREMENTS:\n"
        "- Use nested nodes for the device:\n"
        "  node \"Android Device\" {\n"
        "    node \"App Process\" {\n"
        "      artifact \"AppName.apk\"\n"
        "      component [Room DB] <<SQLite>>\n"
        "    }\n"
        "  }\n"
        "- Use proper shapes for external systems:\n"
        "  * database \"DB Name\" for databases\n"
        "  * cloud \"Service Name\" for cloud services (Firebase, AWS, etc.)\n"
        "  * node \"Server Name\" for REST API backends\n"
        "- Label ALL connections with protocol and library:\n"
        "  app --> api_server : HTTPS\\n(Retrofit + OkHttp)\n"
        "- Show artifacts inside nodes: artifact \"SharedPreferences\"\n"
        "- Include all external connections found in code: APIs, Firebase, analytics SDKs, ad networks\n"
        "- Add 'note right of node : ...' describing the purpose\n\n"
        "STYLING (include at the top after @startuml):\n"
        "  skinparam node {\n"
        "    BackgroundColor #1a1a2e\n"
        "    BorderColor #7c3aed\n"
        "    FontColor #e2e8f0\n"
        "  }\n"
        "  skinparam database {\n"
        "    BackgroundColor #0f172a\n"
        "    BorderColor #06b6d4\n"
        "    FontColor #e2e8f0\n"
        "  }\n"
        "  skinparam cloud {\n"
        "    BackgroundColor #1e293b\n"
        "    BorderColor #4ade80\n"
        "    FontColor #e2e8f0\n"
        "  }\n\n"
        "DO: Show all external services and their connection protocols.\n"
        "DO: Use proper shapes (database, cloud, node, artifact).\n"
        "DO NOT: Include any explanation text, only output PlantUML between @startuml and @enduml.\n"
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
