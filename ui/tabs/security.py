import streamlit as st
from generators import security_scanner
from ui.sidebar import _cached_ollama_status
import config

def render():
    """Renders the Security & Code Quality tab."""
    st.markdown(
        '<div class="section-header">'
        '<span class="icon">🛡️</span>'
        '<span class="title">Security & Code Quality Scanner</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "AI-powered security audit and code smell detection. "
        "Scans are performed using intelligent retrieval of relevant code, "
        "with the LLM acting as a senior security auditor."
    )

    scan_mode = st.radio(
        "Scan Mode:",
        ["Single Category", "Full Scan (Parallel ⚡)"],
        horizontal=True, key="scan_mode",
    )

    if scan_mode == "Single Category":
        cat_options = {
            f"{icon} {name}": key
            for key, name, icon, _, _, _, _ in security_scanner.SCAN_CATEGORIES
        }
        selected_cat_display = st.selectbox(
            "Scan Category:",
            list(cat_options.keys()),
            key="scan_cat_select",
        )
        selected_cat_key = cat_options[selected_cat_display]

        # Show category description
        for key, name, icon, desc, _, _, _ in security_scanner.SCAN_CATEGORIES:
            if key == selected_cat_key:
                st.info(f"**{icon} {name}:** {desc}")
                break

        with st.popover("🔍 Run Scan"):
            status = _cached_ollama_status()
            models = status.get("models", [])
            if not models:
                models = [config.LLM_MODEL]
            
            default_model = getattr(config, "MODEL_ROUTING", {}).get(selected_cat_key, config.LLM_MODEL)
            idx = models.index(default_model) if default_model in models else 0
            selected_model = st.selectbox("LLM Model:", models, index=idx, key="sec_single_mod")
            
            if st.button("Confirm Generate", key="run_single_scan_btn"):
                st.session_state["do_run_single_scan"] = selected_model

        if st.session_state.get("do_run_single_scan"):
            selected_model = st.session_state.pop("do_run_single_scan")
            with st.spinner(f"Scanning {selected_cat_display} ({selected_model})…"):
                result = security_scanner.scan_category(selected_cat_key, target_model=selected_model)

            if result.get("error"):
                st.error(f"Scan error: {result['error']}")
            else:
                findings = result.get("findings", [])
                if not findings:
                    st.success("No issues found! Your code looks clean. ✅")
                else:
                    st.warning(f"Found **{len(findings)}** issue(s).")
                    for i, f in enumerate(findings, 1):
                        sev = f.get("severity", "INFO")
                        sev_lower = sev.lower()
                        sev_icon = security_scanner.SEVERITY_ICONS.get(sev, "⚪")
                        st.markdown(
                            f'<div class="finding-card sev-border-{sev_lower}">'
                            f'<span class="sev-badge sev-{sev_lower}">{sev}</span> '
                            f'<strong>{sev_icon} {f.get("title", "Untitled")}</strong>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if f.get("location") and f["location"] != "N/A":
                            st.markdown(f"**Location:** `{f['location']}`")
                        if f.get("description"):
                            st.markdown(f"{f['description']}")
                        if f.get("recommendation"):
                            with st.expander("💡 Recommendation", expanded=False):
                                st.markdown(f["recommendation"])
                        st.markdown(
                            '<div class="section-divider"></div>',
                            unsafe_allow_html=True,
                        )

                # Raw response
                with st.expander("📄 Raw LLM Response", expanded=False):
                    st.code(result.get("raw_response", ""), language="json")

    else:
        # Full parallel scan
        st.caption(
            f"All **{len(security_scanner.SCAN_CATEGORIES)}** categories will "
            f"be scanned concurrently using "
            f"**{config.PARALLEL_MAX_WORKERS} threads**."
        )

        # Category picker for full scan
        all_cat_keys = [c[0] for c in security_scanner.SCAN_CATEGORIES]
        all_cat_labels = {
            c[0]: f"{c[2]} {c[1]}" for c in security_scanner.SCAN_CATEGORIES
        }
        selected_cats = st.multiselect(
            "Categories to scan:",
            all_cat_keys,
            default=all_cat_keys,
            format_func=lambda k: all_cat_labels[k],
            key="scan_cats_multi",
        )

        with st.popover("🚀 Run Full Scan", disabled=len(selected_cats) == 0):
            status = _cached_ollama_status()
            models = status.get("models", [])
            if not models:
                models = [config.LLM_MODEL]
            selected_model_batch = st.selectbox("LLM Model (for all):", models, key="sec_batch_mod")
            if st.button("Confirm Batch Run", key="run_batch_scan_btn"):
                st.session_state["do_run_batch_scan"] = selected_model_batch

        if st.session_state.get("do_run_batch_scan"):
            selected_model = st.session_state.pop("do_run_batch_scan")
            progress = st.progress(0, text=f"Starting security scan ({selected_model})…")
            step_count = [0]
            total_cats = len(selected_cats)

            def _scan_progress(msg):
                step_count[0] += 1
                progress.progress(
                    min(step_count[0] / total_cats, 1.0),
                    text=msg,
                )

            with st.spinner(
                f"Scanning {total_cats} categories in parallel…"
            ):
                scan_results = security_scanner.scan_all(
                    category_keys=selected_cats,
                    progress_callback=_scan_progress,
                    target_model=selected_model,
                )
            progress.progress(1.0, text="✅ Scan complete!")

            # ── Health Score Dashboard ──
            summary = security_scanner.compute_scan_summary(scan_results)

            st.markdown('<div class="section-divider"></div>',
                        unsafe_allow_html=True)

            score_col, grade_col, findings_col, clean_col = st.columns(4)
            with score_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["health_score"]}</div>'
                    f'<div class="label">Health Score</div></div>',
                    unsafe_allow_html=True,
                )
            with grade_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["health_grade"]}</div>'
                    f'<div class="label">Grade</div></div>',
                    unsafe_allow_html=True,
                )
            with findings_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["total_findings"]}</div>'
                    f'<div class="label">Total Findings</div></div>',
                    unsafe_allow_html=True,
                )
            with clean_col:
                st.markdown(
                    f'<div class="health-card">'
                    f'<div class="score">{summary["categories_clean"]}'
                    f'/{summary["categories_scanned"]}</div>'
                    f'<div class="label">Clean Categories</div></div>',
                    unsafe_allow_html=True,
                )

            # ── Severity Breakdown ──
            st.markdown("### Severity Breakdown")
            sev_cols = st.columns(5)
            for col, sev in zip(
                sev_cols,
                ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
            ):
                count = summary["by_severity"].get(sev, 0)
                sev_icon = security_scanner.SEVERITY_ICONS.get(sev, "⚪")
                with col:
                    st.metric(
                        f"{sev_icon} {sev}",
                        count,
                    )

            st.markdown('<div class="section-divider"></div>',
                        unsafe_allow_html=True)

            # ── Per-Category Results ──
            st.markdown("### Detailed Findings")
            for cat in security_scanner.SCAN_CATEGORIES:
                cat_key = cat[0]
                if cat_key not in scan_results:
                    continue
                result = scan_results[cat_key]
                findings = result.get("findings", [])
                error = result.get("error")
                icon = result.get("icon", cat[2])
                display_name = result.get("display_name", cat[1])

                badge = (
                    "✅ Clean" if not findings and not error
                    else f"⚠️ {len(findings)} issue(s)"
                    if findings
                    else f"❌ Error"
                )

                with st.expander(
                    f"{icon} {display_name} — {badge}",
                    expanded=bool(findings),
                ):
                    if error:
                        st.error(f"Scan error: {error}")
                    elif not findings:
                        st.success("No issues detected.")
                    else:
                        for i, f in enumerate(findings, 1):
                            sev = f.get("severity", "INFO")
                            sev_lower = sev.lower()
                            sev_icon_f = security_scanner.SEVERITY_ICONS.get(
                                sev, "⚪"
                            )
                            st.markdown(
                                f'<div class="finding-card '
                                f'sev-border-{sev_lower}">'
                                f'<span class="sev-badge '
                                f'sev-{sev_lower}">{sev}</span> '
                                f'<strong>{sev_icon_f} '
                                f'{f.get("title", "Untitled")}'
                                f'</strong></div>',
                                unsafe_allow_html=True,
                            )
                            if (
                                f.get("location")
                                and f["location"] != "N/A"
                            ):
                                st.markdown(
                                    f"**Location:** `{f['location']}`"
                                )
                            if f.get("description"):
                                st.markdown(f["description"])
                            if f.get("recommendation"):
                                st.caption(
                                    f"💡 **Fix:** {f['recommendation']}"
                                )
                            if i < len(findings):
                                st.markdown("---")

            # ── Download Report ──
            st.markdown('<div class="section-divider"></div>',
                        unsafe_allow_html=True)
            report_md = security_scanner.generate_scan_report(scan_results)
            st.download_button(
                "📥 Download Full Report (.md)",
                report_md,
                file_name="security_scan_report.md",
                mime="text/markdown",
                key="dl_security_report",
            )
