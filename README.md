# 🤖 RAG-ProjectVisualizer

> **AI-powered Android codebase analysis tool** — understand, document, and visualize any Android project using local LLMs, RAG (Retrieval-Augmented Generation), and automatic diagram generation.

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Setting Up Local LLMs with Ollama](#-setting-up-local-llms-with-ollama)
- [Running the App](#-running-the-app)
- [Configuration](#-configuration)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [Environment Variables](#-environment-variables)

---

## 🔍 Overview

**RAG-ProjectVisualizer** is a fully local, privacy-first tool for deep analysis of Android projects. You point it at any Android codebase (Java/Kotlin), and it:

1. **Parses and indexes** all source files into a local vector database (ChromaDB)
2. **Generates UML diagrams** (class, sequence, activity, state, component, use-case, package, deployment, navigation) using PlantUML
3. **Builds dependency graphs** via Graphviz
4. **Runs a multi-category security and code-quality audit** — detecting hardcoded secrets, insecure network calls, SQL injection, memory leaks, SOLID violations, and more
5. **Auto-generates structured documentation** covering architecture, features, screens, tech stack, data flow, and APIs
6. **Lets you chat with your codebase** through a RAG-powered Q&A interface

Everything runs **100% locally** — no data leaves your machine. All LLM inference is done through [Ollama](https://ollama.com).

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Project Overview** | Indexed file count, chunk statistics, and language breakdown |
| 📐 **UML Diagrams** | 9+ diagram types auto-generated from source code using PlantUML |
| 🔗 **Dependency Graph** | Visual Graphviz rendering of module and class dependencies |
| 🛡️ **Code Quality & Security** | 10-category audit: secrets, SQL injection, memory leaks, SOLID, anti-patterns, and more |
| 📖 **Auto Documentation** | Architecture, feature list, screen inventory, tech stack, data flow, and API docs |
| 💬 **RAG Chat** | Conversational Q&A with context retrieved from your indexed codebase |
| 🕒 **Project History** | Resume previously analyzed projects without re-indexing |
| ⚙️ **Smart Model Routing** | Each task type (diagram, security, chat) is routed to the best-fit local model |

---

## 🏗️ Architecture

```
RAG-ProjectVisualizer/
├── app.py                  ← Streamlit entry point
├── config.py               ← Central configuration & model routing
│
├── core/                   ← RAG pipeline internals
│   ├── parser.py           ← File scanner & language parser
│   ├── chunker.py          ← Smart code chunker
│   ├── embeddings.py       ← Embedding generation (Ollama)
│   ├── vector_store.py     ← ChromaDB wrapper
│   ├── ollama_client.py    ← LLM API client
│   └── rag_engine.py       ← Main orchestration: index + query
│
├── generators/             ← AI generation modules
│   ├── plantuml_gen.py     ← PlantUML diagram generation
│   ├── graphviz_gen.py     ← Dependency graph generation
│   ├── security_scanner.py ← Multi-category security audit
│   ├── doc_generator.py    ← Documentation generation
│   ├── uml_compiler.py     ← UML compilation & normalization
│   ├── uml_ir.py           ← UML intermediate representation
│   ├── uml_normalizer.py   ← Diagram post-processing
│   ├── uml_prompts.py      ← Prompts for each diagram type
│   ├── uml_validator.py    ← Diagram syntax validation
│   └── analysis.py         ← Code complexity analysis
│
├── ui/                     ← Streamlit UI layer
│   ├── styles.py           ← Custom CSS / dark theme
│   ├── sidebar.py          ← Sidebar controls
│   └── tabs/               ← One file per tab
│       ├── overview.py
│       ├── uml.py
│       ├── dependencies.py
│       ├── security.py
│       ├── docs.py
│       ├── chat.py
│       └── history.py
│
└── utils/                  ← Shared utilities
    ├── helpers.py
    ├── history_manager.py
    ├── parallel.py         ← Parallel LLM task execution
    └── plantuml_renderer.py
```

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| **UI Framework** | [Streamlit](https://streamlit.io) ≥ 1.30 |
| **LLM Backend** | [Ollama](https://ollama.com) (local inference) |
| **Vector Database** | [ChromaDB](https://www.trychroma.com) ≥ 0.4.22 |
| **Embedding Model** | `mxbai-embed-large` (via Ollama) |
| **Primary Chat/Diagram Model** | `qwen2.5-coder` |
| **Security/Analysis Model** | `deepseek-coder` |
| **Diagram Rendering** | PlantUML + [Kroki.io](https://kroki.io) |
| **Dependency Graphs** | [Graphviz](https://graphviz.org) |
| **PDF Export** | WeasyPrint |
| **Language Support** | Java, Kotlin, XML, Gradle, `.properties` |

---

## ✅ Prerequisites

Before you begin, make sure you have:

- **Python 3.10+**
- **[Ollama](https://ollama.com/download)** installed and running
- **[Graphviz](https://graphviz.org/download/)** installed and added to your system `PATH`
- At least **8 GB of RAM** (16 GB recommended for running two models concurrently)
- The required Ollama models pulled (see below)

---

## 📦 Installation

### 1. Clone the repository

```bash
git clone https://github.com/Rudraksh2605/RAG-ProjectVisualizer.git
cd RAG-ProjectVisualizer
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

> **Note for Windows users:** If `weasyprint` installation fails, follow the [WeasyPrint Windows installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows).

---

## 🦙 Setting Up Local LLMs with Ollama

The app uses two local models via Ollama. Install Ollama first, then pull the models:

### Option A — Pull from Ollama Hub (recommended for quick start)

```bash
# Chat, diagrams, and documentation
ollama pull qwen2.5-coder

# Security scans, activity diagrams, and code analysis
ollama pull deepseek-coder

# Embedding model
ollama pull mxbai-embed-large
```

### Option B — Load custom GGUF models (for performance tuning)

If you have downloaded GGUF model files locally, use the provided Modelfiles:

```bash
# Edit Modelfile-qwen to point to your local GGUF path, then:
ollama create qwen2.5-coder -f Modelfile-qwen

# Edit Modelfile-deepseek similarly, then:
ollama create deepseek-coder -f Modelfile-deepseek
```

### Verify Ollama is running

```bash
ollama list   # Should show your pulled/created models
```

---

## 🚀 Running the App

Make sure Ollama is running in the background, then:

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

### Using the App

1. **Enter your Android project path** in the sidebar (e.g., `C:\Projects\MyAndroidApp` or `/home/user/projects/MyApp`)
2. Click **Analyze Project** — the engine will parse, chunk, and embed all source files
3. Navigate the tabs:
   - **📊 Overview** — file statistics and project summary
   - **📐 Diagrams** — select and generate any UML diagram type
   - **🔗 Dependency Graph** — visual module dependency map
   - **🛡️ Code Quality** — run security and quality audit categories
   - **📖 Documentation** — auto-generate structured docs (exportable as PDF)
   - **💬 Chat** — ask natural language questions about your codebase
   - **🕒 History** — revisit and resume previously analyzed projects

---

## ⚙️ Configuration

All configuration lives in `config.py`. You can override any value using environment variables without touching the source code.

### Model Routing

Each task is routed to the most suitable model:

| Task Category | Default Model |
|---|---|
| Chat, class diagram, sequence diagram | `qwen2.5-coder` |
| Activity diagram, use-case diagram | `deepseek-coder` |
| Security scans (all 9 categories) | `deepseek-coder` |
| Documentation generation | `qwen2.5-coder` |

To override the default model for all tasks:

```bash
export RPV_LLM_MODEL=your-model-name
```

---

## 🌍 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RPV_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `RPV_OLLAMA_KEEP_ALIVE` | `30m` | How long Ollama keeps models loaded |
| `RPV_LLM_MODEL` | `deepseek-coder` | Fallback LLM model |
| `RPV_EMBEDDING_MODEL` | `mxbai-embed-large:latest` | Embedding model name |
| `RPV_LLM_TEMPERATURE` | `0.3` | Generation temperature |
| `RPV_LLM_CONTEXT_SIZE` | `8192` | Context window size (tokens) |
| `RPV_LLM_MAX_TOKENS` | `2048` | Max tokens per generation |
| `RPV_CHUNK_MAX_CHARS` | `1500` | Max characters per code chunk |
| `RPV_RAG_TOP_K` | `8` | Number of chunks retrieved per query |
| `RPV_PARALLEL_MAX_WORKERS` | `2` | Parallel LLM workers for batch tasks |
| `RPV_KROKI_URL` | `https://kroki.io/plantuml/png` | PlantUML rendering service |
| `RPV_PLANTUML_SERVER` | `http://www.plantuml.com/plantuml` | Fallback PlantUML server |

Set these in your shell before launching, or create a `.env` file and load it manually.

---

## 🔒 Privacy & Data

- **No data is sent to any cloud service.** All LLM inference runs locally via Ollama.
- Diagram rendering uses the public [Kroki.io](https://kroki.io) / PlantUML service — only the PlantUML *markup text* is sent, not your source code.
- Vector embeddings and chunked code are stored locally in `.chroma_db/` inside the project folder.

---

## 🙏 Acknowledgements

- [Ollama](https://ollama.com) for making local LLM inference seamless
- [ChromaDB](https://www.trychroma.com) for the embedded vector store
- [Streamlit](https://streamlit.io) for the rapid UI framework
- [Kroki.io](https://kroki.io) for diagram rendering
- [Qwen2.5-Coder](https://huggingface.co/Qwen) and [DeepSeek-Coder](https://huggingface.co/deepseek-ai) for the open-weight models
