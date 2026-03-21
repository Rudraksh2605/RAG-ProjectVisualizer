"""
Security & Code Smell Scanner — production-grade code quality analyzer.

Uses RAG to retrieve relevant code chunks and asks the LLM to identify
security vulnerabilities, anti-patterns, code smells, and best-practice
violations specific to Android development.

Features:
  - 10 scan categories with dedicated RAG prompts
  - Severity levels (CRITICAL / HIGH / MEDIUM / LOW / INFO)
  - Parallel scanning of multiple categories via ThreadPoolExecutor
  - Structured JSON output parsing from LLM responses
  - Summary statistics and per-finding detail views
"""

import json
import re
from typing import Dict, List, Optional, Callable

from core import rag_engine
from utils.parallel import run_parallel
import config


# ═══════════════════════════════════════════════════════════════
#  Scan Categories
# ═══════════════════════════════════════════════════════════════

# Each entry:  (key, display_name, icon, description, analysis_type,
#               top_k, layer_filter)
SCAN_CATEGORIES = [
    (
        "hardcoded_secrets",
        "Hardcoded Secrets & API Keys",
        "🔑",
        "Finds hardcoded API keys, tokens, passwords, and secrets "
        "that should be in BuildConfig or local.properties.",
        "sec_hardcoded_secrets",
        12, None,
    ),
    (
        "insecure_network",
        "Insecure Network Communication",
        "🌐",
        "Detects plain-text HTTP usage, missing certificate pinning, "
        "disabled SSL verification, and insecure WebSocket connections.",
        "sec_insecure_network",
        10, None,
    ),
    (
        "sql_injection",
        "SQL Injection & DB Vulnerabilities",
        "💉",
        "Identifies raw SQL queries with string concatenation, "
        "missing parameterized queries, and unprotected ContentProviders.",
        "sec_sql_injection",
        10, "Data",
    ),
    (
        "data_exposure",
        "Sensitive Data Exposure",
        "📱",
        "Finds logging of sensitive info, unencrypted SharedPreferences, "
        "data written to external storage without encryption.",
        "sec_data_exposure",
        12, None,
    ),
    (
        "permission_misuse",
        "Permission Misuse & Over-Requesting",
        "🔒",
        "Checks for dangerous permissions requested but unused, "
        "missing runtime permission checks, and exported components.",
        "sec_permission_misuse",
        10, None,
    ),
    (
        "memory_leaks",
        "Memory Leaks & Resource Management",
        "🧠",
        "Detects static Activity/Context references, unclosed resources, "
        "missing lifecycle cleanup, and Handler/AsyncTask leaks.",
        "sec_memory_leaks",
        12, None,
    ),
    (
        "solid_violations",
        "SOLID Principle Violations",
        "📐",
        "Identifies God classes, Single Responsibility violations, "
        "tight coupling, and dependency inversion issues.",
        "sec_solid_violations",
        12, None,
    ),
    (
        "android_antipatterns",
        "Android Anti-Patterns",
        "⚠️",
        "Finds NetworkOnMainThread risks, missing null checks, "
        "deprecated API usage, and hardcoded dimensions/strings in layouts.",
        "sec_android_antipatterns",
        12, None,
    ),
    (
        "error_handling",
        "Error Handling & Crash Risks",
        "💥",
        "Identifies empty catch blocks, generic Exception catching, "
        "missing try-catch around IO/network ops, and swallowed errors.",
        "sec_error_handling",
        10, None,
    ),
    (
        "performance",
        "Performance Issues",
        "⚡",
        "Detects inefficient loops, redundant object creation, "
        "unnecessary synchronization, and missing view recycling.",
        "sec_performance",
        12, None,
    ),
]


# ═══════════════════════════════════════════════════════════════
#  Severity Definitions
# ═══════════════════════════════════════════════════════════════

SEVERITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFO": 4,
}

SEVERITY_COLORS = {
    "CRITICAL": "#dc2626",
    "HIGH": "#ea580c",
    "MEDIUM": "#d97706",
    "LOW": "#2563eb",
    "INFO": "#6b7280",
}

SEVERITY_ICONS = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🔵",
    "INFO": "⚪",
}


# ═══════════════════════════════════════════════════════════════
#  Single Category Scan
# ═══════════════════════════════════════════════════════════════

def scan_category(category_key: str,
                  _prebuilt_context: str = None,
                  target_model: str = None) -> Dict:
    """
    Run a security/code-quality scan for a single category.

    If *_prebuilt_context* is supplied (by scan_all), it skips the
    RAG retrieval step and uses the pre-fetched context directly,
    avoiding redundant embedding+search calls across categories.

    Returns a dict with:
      - category: category key
      - display_name: human-readable name
      - icon: emoji icon
      - findings: list of finding dicts
      - raw_response: the raw LLM output
      - error: error string if scan failed
    """
    cat = _get_category(category_key)
    if not cat:
        return {"category": category_key, "error": "Unknown category"}

    key, display_name, icon, desc, analysis_type, top_k, layer_filter = cat

    question = (
        f"Perform a thorough security and code quality audit for: "
        f"{display_name}. {desc}\n\n"
        f"Analyze the provided code context and identify ALL issues. "
        f"For each finding, provide:\n"
        f"1. SEVERITY: one of CRITICAL, HIGH, MEDIUM, LOW, INFO\n"
        f"2. TITLE: short one-line title\n"
        f"3. LOCATION: class name, method name, or file where the issue is\n"
        f"4. DESCRIPTION: detailed explanation of the vulnerability or smell\n"
        f"5. RECOMMENDATION: specific fix with code example if possible\n\n"
        f"Format your response as a JSON array of objects with keys: "
        f"severity, title, location, description, recommendation.\n"
        f"If NO issues are found, return an empty JSON array: []\n"
        f"Output ONLY the JSON array, no other text."
    )

    try:
        if _prebuilt_context is not None:
            # Fast path: skip retrieval, go straight to LLM generation
            from core.rag_engine import _build_prompt
            from core.ollama_client import generate
            prompt = _build_prompt(question, _prebuilt_context, analysis_type)
            if target_model is None:
                target_model = getattr(config, "MODEL_ROUTING", {}).get(
                    analysis_type, config.LLM_MODEL
                )
            raw = generate(prompt, model=target_model)
        else:
            # Normal path: full RAG query (embed → retrieve → generate)
            raw = rag_engine.query(
                question,
                analysis_type=analysis_type,
                top_k=top_k,
                layer_filter=layer_filter,
                target_model=target_model,
            )
        findings = _parse_findings(raw)
        # Sort by severity
        findings.sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity", "INFO"), 4))

        return {
            "category": key,
            "display_name": display_name,
            "icon": icon,
            "findings": findings,
            "raw_response": raw,
            "error": None,
        }
    except Exception as e:
        return {
            "category": key,
            "display_name": display_name,
            "icon": icon,
            "findings": [],
            "raw_response": "",
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════
#  Full Scan (Parallel)
# ═══════════════════════════════════════════════════════════════

def scan_all(
    category_keys: Optional[List[str]] = None,
    progress_callback: Optional[Callable] = None,
    target_model: str = None,
) -> Dict[str, Dict]:
    """
    Run multiple scan categories in parallel.

    Performance: pre-retrieves shared code context once and reuses
    it across categories that share the same layer_filter, avoiding
    redundant embedding + vector search calls.

    Parameters
    ----------
    category_keys : list of str, optional
        Which categories to scan. If None, scans all.
    progress_callback : callable, optional
        Called with a status message after each scan completes.

    Returns
    -------
    dict  {category_key: scan_result_dict}
    """
    if category_keys is None:
        category_keys = [c[0] for c in SCAN_CATEGORIES]

    # ── Pre-retrieve shared context per unique (layer_filter, top_k) ──
    from core import embeddings, vector_store
    from core.rag_engine import _format_retrieved_context

    context_cache = {}  # (layer_filter, top_k) -> formatted context string
    for key in category_keys:
        cat = _get_category(key)
        if not cat:
            continue
        _, _, _, _, _, top_k, layer_filter = cat
        cache_key = (layer_filter, top_k)
        if cache_key not in context_cache:
            try:
                q_emb = embeddings.embed_text("security code quality audit")
                where = {"layer": layer_filter} if layer_filter else None
                results = vector_store.search(q_emb, top_k=top_k, where=where)
                context_cache[cache_key] = _format_retrieved_context(results)
            except Exception:
                context_cache[cache_key] = None  # fallback to full query

    # ── Build tasks with pre-fetched context ──
    def _make_scan_task(k):
        cat = _get_category(k)
        if not cat:
            return lambda: scan_category(k, target_model=target_model)
        _, _, _, _, _, top_k, layer_filter = cat
        ctx = context_cache.get((layer_filter, top_k))
        return lambda: scan_category(k, _prebuilt_context=ctx, target_model=target_model)

    tasks = [(key, _make_scan_task(key)) for key in category_keys]

    results = run_parallel(
        tasks,
        max_workers=config.PARALLEL_MAX_WORKERS,
        progress_callback=progress_callback,
    )
    return results


# ═══════════════════════════════════════════════════════════════
#  Statistics & Report Generation
# ═══════════════════════════════════════════════════════════════

def compute_scan_summary(scan_results: Dict[str, Dict]) -> Dict:
    """
    Aggregate statistics from a full scan.

    Returns dict with:
      - total_findings: int
      - by_severity: {severity: count}
      - by_category: {category_display_name: count}
      - health_score: int (0-100)
      - health_grade: str (A-F)
      - categories_scanned: int
      - categories_clean: int
    """
    total = 0
    by_severity = {s: 0 for s in SEVERITY_ORDER}
    by_category = {}

    for key, result in scan_results.items():
        findings = result.get("findings", [])
        count = len(findings)
        total += count
        by_category[result.get("display_name", key)] = count
        for f in findings:
            sev = f.get("severity", "INFO").upper()
            if sev in by_severity:
                by_severity[sev] += 1

    # Health score: start at 100, deduct per finding by severity
    deductions = {
        "CRITICAL": 15,
        "HIGH": 8,
        "MEDIUM": 4,
        "LOW": 2,
        "INFO": 0,
    }
    score = 100
    for sev, count in by_severity.items():
        score -= deductions.get(sev, 0) * count
    score = max(0, min(100, score))

    # Grade from score
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 65:
        grade = "C"
    elif score >= 50:
        grade = "D"
    else:
        grade = "F"

    categories_clean = sum(
        1 for r in scan_results.values()
        if len(r.get("findings", [])) == 0 and not r.get("error")
    )

    return {
        "total_findings": total,
        "by_severity": by_severity,
        "by_category": by_category,
        "health_score": score,
        "health_grade": grade,
        "categories_scanned": len(scan_results),
        "categories_clean": categories_clean,
    }


def generate_scan_report(scan_results: Dict[str, Dict]) -> str:
    """
    Generate a downloadable Markdown report from scan results.
    """
    summary = compute_scan_summary(scan_results)
    lines = [
        "# 🛡️ Security & Code Quality Report\n",
        f"**Health Score:** {summary['health_score']}/100 "
        f"(Grade: **{summary['health_grade']}**)\n",
        f"**Total Findings:** {summary['total_findings']}  |  "
        f"**Categories Scanned:** {summary['categories_scanned']}  |  "
        f"**Clean Categories:** {summary['categories_clean']}\n",
        "## Severity Breakdown\n",
        "| Severity | Count |",
        "|----------|-------|",
    ]
    for sev in SEVERITY_ORDER:
        count = summary["by_severity"].get(sev, 0)
        if count > 0:
            lines.append(f"| {SEVERITY_ICONS.get(sev, '')} {sev} | {count} |")

    lines.append("")
    lines.append("---\n")

    # Per-category details
    for cat_key, cat_name, icon, _, _, _, _ in SCAN_CATEGORIES:
        result = scan_results.get(cat_key)
        if not result:
            continue

        findings = result.get("findings", [])
        error = result.get("error")

        lines.append(f"## {icon} {cat_name}\n")
        if error:
            lines.append(f"> **Error:** {error}\n")
            continue
        if not findings:
            lines.append("No issues found. ✅\n")
            continue

        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "INFO")
            sev_icon = SEVERITY_ICONS.get(sev, "⚪")
            lines.append(
                f"### {i}. {sev_icon} [{sev}] {f.get('title', 'Untitled')}\n"
            )
            if f.get("location"):
                lines.append(f"**Location:** `{f['location']}`\n")
            if f.get("description"):
                lines.append(f"{f['description']}\n")
            if f.get("recommendation"):
                lines.append(f"**Recommendation:** {f['recommendation']}\n")
            lines.append("---\n")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Internal Helpers
# ═══════════════════════════════════════════════════════════════

def _get_category(key: str):
    """Look up a scan category by key."""
    for cat in SCAN_CATEGORIES:
        if cat[0] == key:
            return cat
    return None


def _parse_findings(raw: str) -> List[Dict]:
    """
    Extract structured findings from LLM output.

    The model is asked to return a JSON array. This function handles
    various common LLM response formats:
      1. Clean JSON array
      2. JSON inside code fences
      3. JSON with leading/trailing text
      4. Fallback: return raw text as a single INFO finding
    """
    text = raw.strip()

    # Try to extract JSON from code fences first
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try to find JSON array bounds
    arr_start = text.find('[')
    arr_end = text.rfind(']')

    if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        json_str = text[arr_start:arr_end + 1]
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                return _normalize_findings(parsed)
        except json.JSONDecodeError:
            pass

    # Try parsing the whole text as JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return _normalize_findings(parsed)
        if isinstance(parsed, dict):
            return _normalize_findings([parsed])
    except json.JSONDecodeError:
        pass

    # Fallback: wrap raw response as a single text finding
    if text and text != "[]":
        return [{
            "severity": "INFO",
            "title": "Scan Results (unstructured)",
            "location": "N/A",
            "description": text[:2000],
            "recommendation": "Review the findings above manually.",
        }]

    return []


def _normalize_findings(findings: List) -> List[Dict]:
    """
    Normalize and validate each finding dict from LLM output.
    Ensures all fields exist with correct types.
    """
    normalized = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        severity = str(f.get("severity", "INFO")).upper().strip()
        if severity not in SEVERITY_ORDER:
            severity = "INFO"

        normalized.append({
            "severity": severity,
            "title": str(f.get("title", "Untitled finding")).strip(),
            "location": str(f.get("location", "Unknown")).strip(),
            "description": str(f.get("description", "")).strip(),
            "recommendation": str(f.get("recommendation", "")).strip(),
        })
    return normalized
