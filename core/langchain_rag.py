"""
LangChain RAG — replaces the manual query pipeline for the Chat tab.

Provides:
  1. Hybrid retrieval (ChromaDB vector search + Neo4j Cypher graph queries)
  2. LangChain chains with ChatOllama for structured prompt engineering
  3. Streaming support for the Streamlit chat UI
  4. GraphCypherQAChain for structural / dependency questions

The rest of the app (UML generation, security scans, documentation)
continues using ollama_client.py directly — LangChain is only used
where its orchestration adds measurable value.
"""

import logging
import re
from typing import Optional, List, Dict, Generator

log = logging.getLogger("langchain_rag")

# ── Lazy imports to avoid crash if langchain not installed ──────
_LC_AVAILABLE = False
_ChatOllama = None
_OllamaEmbeddings = None
_Chroma = None

try:
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    from langchain_chroma import Chroma
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    _ChatOllama = ChatOllama
    _OllamaEmbeddings = OllamaEmbeddings
    _Chroma = Chroma
    _LC_AVAILABLE = True
    log.info("LangChain loaded successfully.")
except ImportError as e:
    log.warning("LangChain not available (%s). Using native RAG pipeline.", e)


def is_available() -> bool:
    return _LC_AVAILABLE


# ── Module state ───────────────────────────────────────────────
_llm = None
_embeddings = None
_vectorstore = None
_chain = None


def _get_llm(model: str = None):
    """Get or create the ChatOllama LLM instance."""
    global _llm
    import config

    model = model or config.MODEL_ROUTING.get("general", config.LLM_MODEL)

    if _llm is None or _llm.model != model:
        _llm = _ChatOllama(
            model=model,
            base_url=config.OLLAMA_BASE_URL,
            temperature=config.LLM_TEMPERATURE,
            num_predict=config.LLM_MAX_TOKENS,
            num_ctx=config.LLM_CONTEXT_SIZE,
            keep_alive=config.OLLAMA_KEEP_ALIVE,
        )
    return _llm


def _get_embeddings():
    """Get or create the OllamaEmbeddings instance."""
    global _embeddings
    import config

    if _embeddings is None:
        _embeddings = _OllamaEmbeddings(
            model=config.EMBEDDING_MODEL,
            base_url=config.OLLAMA_BASE_URL,
        )
    return _embeddings


def _get_vectorstore():
    """Connect to the existing ChromaDB collection via LangChain."""
    global _vectorstore
    import config

    if _vectorstore is None:
        _vectorstore = _Chroma(
            collection_name=config.CHROMA_COLLECTION_NAME,
            persist_directory=config.CHROMA_PERSIST_DIR,
            embedding_function=_get_embeddings(),
        )
    return _vectorstore


def reset():
    """Reset all LangChain state (call after re-indexing)."""
    global _llm, _embeddings, _vectorstore, _chain
    _llm = None
    _embeddings = None
    _vectorstore = None
    _chain = None


# ── Query Classification ──────────────────────────────────────

_STRUCTURAL_PATTERNS = [
    r"\b(depend|depends|dependency|dependencies)\b",
    r"\b(inherit|extends|subclass|superclass|parent class)\b",
    r"\b(implements|interface)\b",
    r"\b(calls?|invokes?|call chain|call graph)\b",
    r"\b(imports?|imported by)\b",
    r"\bwhat classes\b",
    r"\bwho uses\b",
    r"\bimpact of changing\b",
    r"\bconnected to\b",
    r"\brelationship between\b",
]

_STRUCTURAL_RE = re.compile("|".join(_STRUCTURAL_PATTERNS), re.IGNORECASE)


def _is_structural_query(question: str) -> bool:
    """Detect if a question is about code structure/relationships."""
    return bool(_STRUCTURAL_RE.search(question))


def _extract_class_names(question: str) -> List[str]:
    """Extract potential class names from a question (PascalCase words)."""
    return re.findall(r"\b([A-Z][a-zA-Z0-9]{2,})\b", question)


# ── Hybrid Retrieval ──────────────────────────────────────────

def _retrieve_vector_context(question: str,
                             top_k: int = None,
                             layer_filter: str = None) -> str:
    """Retrieve context from ChromaDB via LangChain."""
    import config
    k = top_k or config.RAG_TOP_K
    vs = _get_vectorstore()

    kwargs = {"k": k}
    if layer_filter:
        kwargs["filter"] = {"layer": layer_filter}

    docs = vs.similarity_search(question, **kwargs)

    blocks = []
    for doc in docs:
        meta = doc.metadata
        header = (
            f"[{meta.get('chunk_type', '?')}] "
            f"{meta.get('component_name', '?')} "
            f"({meta.get('component_type', '?')}, Layer: {meta.get('layer', '?')})"
        )
        blocks.append(f"### {header}\n{doc.page_content}")

    return "\n\n---\n\n".join(blocks) if blocks else "(No relevant context found)"


def _retrieve_graph_context(question: str) -> str:
    """Retrieve structural context from Neo4j knowledge graph."""
    from core import graph_store

    if not graph_store.is_available():
        return ""

    class_names = _extract_class_names(question)
    if not class_names:
        return ""

    graph_blocks = []
    for cls_name in class_names[:3]:  # limit to 3 to avoid bloat
        # Dependencies
        deps = graph_store.get_class_dependencies(cls_name)
        if deps:
            lines = [f"**{cls_name} depends on:**"]
            for d in deps[:10]:
                lines.append(
                    f"  - ({d.get('relationship', '?')}) → "
                    f"{d.get('dep_name', '?')}"
                )
            graph_blocks.append("\n".join(lines))

        # Dependents
        dependents = graph_store.get_class_dependents(cls_name)
        if dependents:
            lines = [f"**Classes that depend on {cls_name}:**"]
            for d in dependents[:10]:
                lines.append(
                    f"  - {d.get('dep_name', '?')} "
                    f"({d.get('relationship', '?')})"
                )
            graph_blocks.append("\n".join(lines))

    return "\n\n".join(graph_blocks) if graph_blocks else ""


def _cypher_query_for_question(question: str) -> str:
    """
    Use the LLM to generate a Cypher query for structural questions,
    then execute it and return the results as formatted text.
    """
    from core import graph_store

    if not graph_store.is_available():
        return ""

    schema = graph_store.get_full_schema_for_cypher()

    cypher_prompt = (
        "You are a Neo4j Cypher expert. Given the following graph schema "
        "and a user question about an Android codebase, write a Cypher query "
        "to answer it.\n\n"
        f"SCHEMA:\n{schema}\n\n"
        f"QUESTION: {question}\n\n"
        "Return ONLY the Cypher query, no explanation. "
        "Use LIMIT 20 to avoid excessive results. "
        "If the question cannot be answered with Cypher, return: NONE"
    )

    try:
        llm = _get_llm()
        result = llm.invoke(cypher_prompt)
        cypher_text = result.content.strip()

        # Clean up code fences
        cypher_text = re.sub(r"```(?:cypher)?\s*\n?", "", cypher_text)
        cypher_text = cypher_text.strip("`").strip()

        if not cypher_text or cypher_text.upper() == "NONE":
            return ""

        # Execute the Cypher query
        records = graph_store.run_cypher(cypher_text)
        if not records:
            return ""

        # Format results
        lines = [f"**Graph Query Results** (Cypher: `{cypher_text}`)"]
        for record in records[:20]:
            parts = []
            for k, v in record.items():
                parts.append(f"{k}: {v}")
            lines.append("  - " + ", ".join(parts))

        return "\n".join(lines)

    except Exception as e:
        log.warning("Cypher generation/execution failed: %s", e)
        return ""


# ── Main Query Interface ──────────────────────────────────────

def hybrid_query(question: str,
                 analysis_type: str = "general",
                 top_k: int = None,
                 layer_filter: str = None,
                 target_model: str = None) -> str:
    """
    Full hybrid RAG query:
      1. Retrieve semantic context from ChromaDB
      2. Retrieve structural context from Neo4j
      3. For structural questions, also run a Cypher query
      4. Combine all context and generate answer via LangChain

    Returns the complete response string.
    """
    if not _LC_AVAILABLE:
        # Fallback to native pipeline
        from core.rag_engine import query as native_query
        return native_query(question, analysis_type=analysis_type,
                            top_k=top_k, layer_filter=layer_filter,
                            target_model=target_model)

    import config

    # 1. Vector context (always)
    vector_ctx = _retrieve_vector_context(question, top_k, layer_filter)

    # 2. Graph context (if available and relevant)
    graph_ctx = ""
    cypher_ctx = ""
    is_structural = _is_structural_query(question)

    if config.GRAPHRAG_ENABLED:
        graph_ctx = _retrieve_graph_context(question)
        if is_structural:
            cypher_ctx = _cypher_query_for_question(question)

    # 3. Combine contexts
    context_parts = [vector_ctx]
    if graph_ctx:
        context_parts.append(
            f"\n\n{'='*40}\nSTRUCTURAL CONTEXT (from Knowledge Graph):\n{'='*40}\n{graph_ctx}"
        )
    if cypher_ctx:
        context_parts.append(
            f"\n\n{'='*40}\nGRAPH QUERY RESULTS:\n{'='*40}\n{cypher_ctx}"
        )

    full_context = "\n".join(context_parts)

    # 4. Build prompt and generate
    model = target_model or config.MODEL_ROUTING.get(analysis_type, config.LLM_MODEL)
    llm = _get_llm(model)

    system_msg = (
        f"You are {model}, an expert AI assistant specialized in Android "
        "code analysis and software architecture. You have been given RELEVANT "
        "EXCERPTS from the project's codebase via a retrieval system, plus "
        "STRUCTURAL DATA from a knowledge graph showing class relationships, "
        "inheritance, method calls, and dependencies.\n\n"
        "Use ALL provided context to answer. Be specific and reference "
        "actual class/method names from the context. When structural data "
        "is available, use it to explain relationships and dependencies."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human",
         "RETRIEVED CODE CONTEXT:\n"
         "{'='*60}\n"
         "{context}\n"
         "{'='*60}\n\n"
         "QUESTION: {question}\n\n"
         "ANSWER:"),
    ])

    chain = prompt | llm | StrOutputParser()

    print(f"\n[LangChain Router] Routing '{analysis_type}' task to model: {model}")
    print(f"  Vector context: {len(vector_ctx)} chars")
    print(f"  Graph context:  {len(graph_ctx)} chars")
    print(f"  Cypher context: {len(cypher_ctx)} chars")
    print(f"  Structural query: {is_structural}")

    return chain.invoke({
        "context": full_context,
        "question": question,
    })


def hybrid_query_stream(question: str,
                        analysis_type: str = "general",
                        top_k: int = None,
                        layer_filter: str = None,
                        target_model: str = None) -> Generator[str, None, None]:
    """
    Streaming version of hybrid_query for the Streamlit chat UI.
    Yields tokens one at a time.
    """
    if not _LC_AVAILABLE:
        from core.rag_engine import query_stream as native_stream
        yield from native_stream(question, analysis_type=analysis_type,
                                 top_k=top_k, layer_filter=layer_filter,
                                 target_model=target_model)
        return

    import config

    # Retrieval (non-streaming)
    vector_ctx = _retrieve_vector_context(question, top_k, layer_filter)

    graph_ctx = ""
    cypher_ctx = ""
    is_structural = _is_structural_query(question)

    if config.GRAPHRAG_ENABLED:
        graph_ctx = _retrieve_graph_context(question)
        if is_structural:
            cypher_ctx = _cypher_query_for_question(question)

    context_parts = [vector_ctx]
    if graph_ctx:
        context_parts.append(
            f"\n\nSTRUCTURAL CONTEXT (from Knowledge Graph):\n{graph_ctx}"
        )
    if cypher_ctx:
        context_parts.append(
            f"\n\nGRAPH QUERY RESULTS:\n{cypher_ctx}"
        )

    full_context = "\n".join(context_parts)

    model = target_model or config.MODEL_ROUTING.get(analysis_type, config.LLM_MODEL)
    llm = _get_llm(model)

    system_msg = (
        f"You are {model}, an expert AI assistant specialized in Android "
        "code analysis and software architecture. You have been given RELEVANT "
        "EXCERPTS from the project's codebase via a retrieval system, plus "
        "STRUCTURAL DATA from a knowledge graph.\n"
        "Use ALL provided context to answer. Be specific."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human",
         "RETRIEVED CODE CONTEXT:\n"
         "{context}\n\n"
         "QUESTION: {question}\n\n"
         "ANSWER:"),
    ])

    chain = prompt | llm | StrOutputParser()

    print(f"\n[LangChain Stream] Routing '{analysis_type}' to model: {model}")

    # Stream tokens
    try:
        for chunk in chain.stream({
            "context": full_context,
            "question": question,
        }):
            if chunk:
                yield chunk
    except Exception as e:
        yield f"\n[LangChain streaming error: {e}]"
