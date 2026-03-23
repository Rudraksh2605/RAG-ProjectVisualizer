"""
Central configuration for RAG-ProjectVisualizer.
All Ollama endpoints, model names, and tuning parameters live here.
"""

# ── Ollama Server ──────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"

# ── Models ─────────────────────────────────────────────────────
LLM_MODEL = "deepseek-coder"           # General fallback

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

EMBEDDING_MODEL = "nomic-embed-text"    # For vector embeddings

# ── Parallel execution ─────────────────────────────────────────
PARALLEL_MAX_WORKERS = 1                # Max concurrent LLM requests (1 for local Ollama to avoid timeouts)

# ── Generation parameters ──────────────────────────────────────
LLM_TEMPERATURE = 0.3
LLM_TOP_P = 0.9
LLM_TOP_K = 40
LLM_REPEAT_PENALTY = 1.1
LLM_CONTEXT_SIZE = 8192
LLM_MAX_TOKENS = 2048

# ── RAG parameters ─────────────────────────────────────────────
CHUNK_MAX_CHARS = 1500          # Max characters per chunk
RAG_TOP_K = 8                   # Number of chunks to retrieve per query
EMBEDDING_DIMENSIONS = 768      # nomic-embed-text output dimensions

# ── ChromaDB ───────────────────────────────────────────────────
CHROMA_PERSIST_DIR = ".chroma_db"
CHROMA_COLLECTION_NAME = "project_chunks"

# ── File scanning ──────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".java", ".kt", ".xml", ".gradle", ".kts", ".properties"}
IGNORE_DIRS = {".git", ".gradle", ".idea", "build", "bin", "node_modules", "__pycache__", ".chroma_db"}
