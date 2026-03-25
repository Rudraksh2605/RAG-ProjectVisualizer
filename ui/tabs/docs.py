import streamlit as st
import io
from generators import doc_generator
from ui.sidebar import _cached_ollama_status
import config


def _markdown_to_pdf(md_text: str) -> bytes:
    """Convert markdown text to a styled PDF.

    Uses markdown → HTML → PDF pipeline.  The HTML is rendered with
    a dark-themed stylesheet that mirrors the app's visual style.
    Falls back gracefully if dependencies are unavailable.
    """
    try:
        import markdown
        from weasyprint import HTML
    except ImportError:
        # Provide a plain-text fallback wrapped in a minimal PDF
        try:
            from weasyprint import HTML
            html_body = f"<pre style='font-family:monospace;font-size:11px;white-space:pre-wrap'>{md_text}</pre>"
            return HTML(string=html_body).write_pdf()
        except ImportError:
            return None

    # Convert markdown to HTML
    html_body = markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
    )

    # Styled HTML document
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 2cm 2.5cm;
        @top-center {{
            content: "Project Documentation";
            font-size: 9px;
            color: #888;
        }}
        @bottom-center {{
            content: counter(page) " / " counter(pages);
            font-size: 9px;
            color: #888;
        }}
    }}
    body {{
        font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #1a1a2e;
        max-width: 100%;
    }}
    h1 {{
        font-size: 22pt;
        color: #1e1e2f;
        border-bottom: 3px solid #7c3aed;
        padding-bottom: 8px;
        margin-top: 0;
    }}
    h2 {{
        font-size: 16pt;
        color: #2d2d44;
        border-bottom: 2px solid #06b6d4;
        padding-bottom: 6px;
        margin-top: 28px;
        page-break-after: avoid;
    }}
    h3 {{
        font-size: 13pt;
        color: #3a3a5c;
        margin-top: 20px;
        page-break-after: avoid;
    }}
    h4 {{
        font-size: 11pt;
        color: #4a4a6a;
        margin-top: 16px;
    }}
    p {{ margin: 8px 0; }}
    ul, ol {{ margin: 6px 0 6px 20px; }}
    li {{ margin: 3px 0; }}
    code {{
        background: #f0f0f5;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 10pt;
    }}
    pre {{
        background: #1e1e2f;
        color: #e0e0e8;
        padding: 14px;
        border-radius: 8px;
        overflow-x: auto;
        font-size: 9.5pt;
        line-height: 1.4;
        page-break-inside: avoid;
    }}
    pre code {{
        background: none;
        padding: 0;
        color: inherit;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 12px 0;
        font-size: 10pt;
    }}
    th {{
        background: #7c3aed;
        color: white;
        padding: 8px 12px;
        text-align: left;
    }}
    td {{
        border: 1px solid #d0d0d8;
        padding: 6px 12px;
    }}
    tr:nth-child(even) td {{ background: #f5f5fa; }}
    hr {{
        border: none;
        border-top: 1px solid #d0d0d8;
        margin: 24px 0;
    }}
    blockquote {{
        border-left: 4px solid #7c3aed;
        margin: 12px 0;
        padding: 8px 16px;
        background: #f5f3ff;
        color: #4a4a6a;
    }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    return HTML(string=full_html).write_pdf()


def render():
    """Renders the Documentation tab."""
    st.markdown("## AI-Generated Documentation")

    doc_mode = st.radio(
        "Mode:", ["Single Section", "Full Report (Parallel ⚡)"],
        horizontal=True, key="doc_mode",
    )

    if doc_mode == "Single Section":
        sec_options = {title: key for key, title, _, _ in doc_generator.SECTIONS}
        selected_title = st.selectbox("Section:", list(sec_options.keys()),
                                      key="doc_section")
        with st.popover("📝 Generate Section"):
            status = _cached_ollama_status()
            models = status.get("models", [])
            if not models:
                models = [config.LLM_MODEL]
            
            default_model = config.LLM_MODEL
            idx = models.index(default_model) if default_model in models else 0
            selected_model = st.selectbox("LLM Model:", models, index=idx, key="doc_single_mod")
            
            if st.button("Confirm Generate", key="gen_doc_single_btn"):
                st.session_state["do_gen_doc_single"] = selected_model
        
        if st.session_state.get("do_gen_doc_single"):
            selected_model = st.session_state.pop("do_gen_doc_single")
            with st.spinner(f"Generating {selected_title} ({selected_model})…"):
                content = doc_generator.generate_section(
                    sec_options[selected_title], target_model=selected_model
                )
            st.markdown(content)
    else:
        st.caption(
            f"All {len(doc_generator.SECTIONS)} sections will be generated "
            f"concurrently using **{config.PARALLEL_MAX_WORKERS} threads**."
        )
        with st.popover("📖 Generate Full Report"):
            status = _cached_ollama_status()
            models = status.get("models", [])
            if not models:
                models = [config.LLM_MODEL]
            selected_model_batch = st.selectbox("LLM Model (for all):", models, key="doc_batch_mod")
            if st.button("Confirm Full Report", key="gen_doc_batch_btn"):
                st.session_state["do_gen_doc_batch"] = selected_model_batch
                
        if st.session_state.get("do_gen_doc_batch"):
            selected_model = st.session_state.pop("do_gen_doc_batch")
            progress = st.progress(0, text=f"Starting parallel generation ({selected_model})…")

            step_count = [0]

            def _doc_progress(msg):
                step_count[0] += 1
                progress.progress(
                    min(step_count[0] / len(doc_generator.SECTIONS), 1.0),
                    text=msg,
                )

            with st.spinner("Generating full report in parallel…"):
                report = doc_generator.generate_full_report(
                    progress_callback=_doc_progress, target_model=selected_model
                )
            progress.progress(1.0, text="✅ Done!")
            st.markdown(report)

            # ── Download buttons ──
            col_md, col_pdf = st.columns(2)

            with col_md:
                st.download_button(
                    "💾 Download Report (.md)", report,
                    file_name="project_documentation.md", mime="text/markdown",
                )

            with col_pdf:
                pdf_bytes = _markdown_to_pdf(report)
                if pdf_bytes:
                    st.download_button(
                        "📄 Export as PDF", pdf_bytes,
                        file_name="project_documentation.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.info(
                        "Install `markdown` and `weasyprint` for PDF export:\n\n"
                        "`pip install markdown weasyprint`"
                    )
