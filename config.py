"""
Central configuration for RAG-ProjectVisualizer.
All Ollama endpoints, model names, and tuning parameters live here.
"""

import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# ── Ollama Server ──────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("RPV_OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_KEEP_ALIVE = os.getenv("RPV_OLLAMA_KEEP_ALIVE", "30m")

# ── Models ─────────────────────────────────────────────────────
LLM_MODEL = os.getenv("RPV_LLM_MODEL", "deepseek-coder")  # General fallback

# Route specific tasks to the model best suited for it
MODEL_ROUTING = {
    "general": "qwen2.5-coder",             # Chat & explanation
    "class_diagram": "qwen2.5-coder",       # PlantUML rendering
    "sequence_diagram": "qwen2.5-coder",
    "activity_diagram": "deepseek-coder",
    "dependency_graph": "qwen2.5-coder",    # Graphviz text
    "state_diagram": "qwen2.5-coder",       # New UML diagrams
    "component_diagram": "qwen2.5-coder",
    "usecase_diagram": "deepseek-coder",
    "package_diagram": "qwen2.5-coder",
    "deployment_diagram": "qwen2.5-coder",
    "navigation_diagram": "deepseek-coder",
    "doc_overview": "qwen2.5-coder",        # Documentation
    "doc_architecture": "qwen2.5-coder",
    "doc_features": "qwen2.5-coder",
    "doc_screens": "qwen2.5-coder",
    "doc_tech_stack": "qwen2.5-coder",
    "doc_data_flow": "qwen2.5-coder",
    "doc_api": "qwen2.5-coder",
    "complexity": "deepseek-coder",         # DeepSeek excels at pure code logic analysis
    # Security & Code Quality scans — DeepSeek excels at code-level analysis
    "sec_hardcoded_secrets": "deepseek-coder",
    "sec_insecure_network": "deepseek-coder",
    "sec_sql_injection": "deepseek-coder",
    "sec_data_exposure": "deepseek-coder",
    "sec_permission_misuse": "deepseek-coder",
    "sec_memory_leaks": "deepseek-coder",
    "sec_solid_violations": "deepseek-coder",
    "sec_android_antipatterns": "deepseek-coder",
    "sec_error_handling": "deepseek-coder",
    "sec_performance": "deepseek-coder",
}

EMBEDDING_MODEL = os.getenv("RPV_EMBEDDING_MODEL", "mxbai-embed-large:latest")
EMBEDDING_GPU_LAYERS = int(os.getenv("RPV_EMBEDDING_GPU_LAYERS", "999"))

# ── Parallel execution ─────────────────────────────────────────
PARALLEL_MAX_WORKERS = max(
    1,
    int(os.getenv("RPV_PARALLEL_MAX_WORKERS", "2")),
)

# ── Generation parameters ──────────────────────────────────────
LLM_TEMPERATURE = float(os.getenv("RPV_LLM_TEMPERATURE", "0.3"))
LLM_TOP_P = float(os.getenv("RPV_LLM_TOP_P", "0.9"))
LLM_TOP_K = int(os.getenv("RPV_LLM_TOP_K", "40"))
LLM_REPEAT_PENALTY = float(os.getenv("RPV_LLM_REPEAT_PENALTY", "1.1"))
LLM_CONTEXT_SIZE = int(os.getenv("RPV_LLM_CONTEXT_SIZE", "8192"))
LLM_MAX_TOKENS = int(os.getenv("RPV_LLM_MAX_TOKENS", "2048"))

# Per-model runtime tuning for slower local models.
DEEPSEEK_UML_CONTEXT_SIZE = int(os.getenv("RPV_DEEPSEEK_UML_CONTEXT_SIZE", "4096"))
DEEPSEEK_UML_MAX_TOKENS = int(os.getenv("RPV_DEEPSEEK_UML_MAX_TOKENS", "1536"))
DEEPSEEK_UML_CONTEXT_MAX_CHARS = int(
    os.getenv("RPV_DEEPSEEK_UML_CONTEXT_MAX_CHARS", "9000")
)
DEEPSEEK_USE_NATIVE_JSON_MODE = _env_bool(
    "RPV_DEEPSEEK_USE_NATIVE_JSON_MODE",
    True,
)
DEEPSEEK_NUM_THREAD = int(
    os.getenv("RPV_DEEPSEEK_NUM_THREAD", str(os.cpu_count() or 8))
)
DEEPSEEK_NUM_BATCH = int(os.getenv("RPV_DEEPSEEK_NUM_BATCH", "512"))
DEEPSEEK_NUM_GPU = os.getenv("RPV_DEEPSEEK_NUM_GPU", "").strip()

MODEL_RUNTIME_PROFILES = {
    "deepseek-coder": {
        "use_native_json_mode": DEEPSEEK_USE_NATIVE_JSON_MODE,
        "num_thread": DEEPSEEK_NUM_THREAD,
        "num_batch": DEEPSEEK_NUM_BATCH,
        "num_gpu": int(DEEPSEEK_NUM_GPU) if DEEPSEEK_NUM_GPU else None,
    },
}

# ── RAG parameters ─────────────────────────────────────────────
CHUNK_MAX_CHARS = int(os.getenv("RPV_CHUNK_MAX_CHARS", "1500"))
RAG_TOP_K = int(os.getenv("RPV_RAG_TOP_K", "8"))
EMBEDDING_DIMENSIONS = int(os.getenv("RPV_EMBEDDING_DIMENSIONS", "1024"))

QUERY_EXPANSION_MODE = os.getenv("RPV_QUERY_EXPANSION_MODE", "auto")
QUERY_CACHE_MAX_ENTRIES = int(os.getenv("RPV_QUERY_CACHE_MAX_ENTRIES", "256"))
EMBED_CACHE_MAX_ENTRIES = int(os.getenv("RPV_EMBED_CACHE_MAX_ENTRIES", "256"))
RETRIEVAL_CACHE_MAX_ENTRIES = int(
    os.getenv("RPV_RETRIEVAL_CACHE_MAX_ENTRIES", "128")
)
RETRIEVED_CONTEXT_MAX_CHARS = int(
    os.getenv("RPV_RETRIEVED_CONTEXT_MAX_CHARS", "12000")
)
UML_CONTEXT_MAX_CHARS = int(os.getenv("RPV_UML_CONTEXT_MAX_CHARS", "14000"))

# ── ChromaDB ───────────────────────────────────────────────────
CHROMA_PERSIST_DIR = ".chroma_db"
CHROMA_COLLECTION_NAME = "project_chunks"

KROKI_URL = os.getenv("RPV_KROKI_URL", "https://kroki.io/plantuml/png")
PLANTUML_SERVER = os.getenv(
    "RPV_PLANTUML_SERVER", "http://www.plantuml.com/plantuml"
)
RENDER_CACHE_MAX_ENTRIES = int(os.getenv("RPV_RENDER_CACHE_MAX_ENTRIES", "128"))

# ── File scanning ──────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".java", ".kt", ".xml", ".gradle", ".kts", ".properties"}
IGNORE_DIRS = {".git", ".gradle", ".idea", "build", "bin", "node_modules", "__pycache__", ".chroma_db"}

# ── Neo4j / GraphRAG ──────────────────────────────────────────
NEO4J_URI = os.getenv("RPV_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("RPV_NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("RPV_NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("RPV_NEO4J_DATABASE", "neo4j")

# When True, system uses hybrid retrieval (ChromaDB + Neo4j).
# When False or Neo4j unavailable, falls back to ChromaDB-only.
GRAPHRAG_ENABLED = _env_bool("RPV_GRAPHRAG_ENABLED", True)

# Max Cypher query results to feed the LLM
GRAPH_TOP_K = int(os.getenv("RPV_GRAPH_TOP_K", "20"))

# ── LangChain ──────────────────────────────────────────────────
# When True, chat queries are routed through LangChain chains.
# UML/security/doc generation still uses ollama_client.py directly.
LANGCHAIN_ENABLED = _env_bool("RPV_LANGCHAIN_ENABLED", True)

