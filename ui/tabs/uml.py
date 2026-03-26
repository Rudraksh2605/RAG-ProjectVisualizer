import streamlit as st
from generators.plantuml_gen import DIAGRAM_REGISTRY
from generators import analysis
from utils.plantuml_renderer import render_to_bytesio
from utils.parallel import run_parallel
from core import rag_engine
import config
from ui.utils import _save_file
from ui.sidebar import _cached_ollama_status

def _render_one(name_puml):
    name, puml = name_puml
    return name, render_to_bytesio(puml)

def render():
    """Renders the Diagrams tab."""
    st.markdown(
        '<div class="section-header">'
        '<span class="icon">📐</span>'
        '<span class="title">Diagrams</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Generate 8 types of architectural diagrams using AI + LLM. "
        "Select a single diagram or use **Batch Generate** to create "
        "multiple diagrams in parallel with threading."
    )

    stats = rag_engine.get_project_stats()
    diagram_names = list(DIAGRAM_REGISTRY.keys())
    class_names = analysis.get_class_list(stats)

    # ── Single diagram generation ──
    st.markdown("### 🎯 Single Diagram")
    col_sel, col_focus = st.columns([1, 1])
    with col_sel:
        selected_diagram = st.selectbox(
            "Diagram Type:",
            diagram_names,
            key="uml_type_select",
        )
    with col_focus:
        gen_func, needs_focus = DIAGRAM_REGISTRY[selected_diagram]
        if needs_focus:
            focus_sel = st.selectbox(
                "Focus on class (optional):",
                ["(All Classes)"] + class_names,
                key="uml_focus_class",
            )
        else:
            focus_sel = None
            st.info(f"ℹ️ {selected_diagram} does not use a focus class.")

    with st.popover("🎨 Generate Diagram"):
        status = _cached_ollama_status()
        models = status.get("models", [])
        if not models:
            models = [config.LLM_MODEL]
        
        default_model = getattr(config, "MODEL_ROUTING", {}).get(selected_diagram, config.LLM_MODEL)
        idx = models.index(default_model) if default_model in models else 0
        selected_model_single = st.selectbox("LLM Model:", models, index=idx, key="uml_single_mod")
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Generate", key="gen_single_uml_btn"):
                st.session_state["do_gen_single_uml"] = selected_model_single
                st.session_state["do_gen_single_force"] = False
        with btn_col2:
            if st.button("Regenerate", key="regen_single_uml_btn"):
                st.session_state["do_gen_single_uml"] = selected_model_single
                st.session_state["do_gen_single_force"] = True

    if st.session_state.get("do_gen_single_uml"):
        selected_model = st.session_state.pop("do_gen_single_uml")
        force_gen = st.session_state.pop("do_gen_single_force", False)
        with st.spinner(f"Generating {selected_diagram} via AI + {selected_model}…"):
            if needs_focus and focus_sel and focus_sel != "(All Classes)":
                puml = gen_func(focus_sel, target_model=selected_model, force=force_gen)
            elif needs_focus:
                puml = gen_func(None, target_model=selected_model, force=force_gen)
            else:
                puml = gen_func(target_model=selected_model, force=force_gen)

        # Store in session state so data survives Streamlit reruns
        st.session_state["last_puml"] = puml
        st.session_state["last_diagram_name"] = selected_diagram

        with st.spinner("Rendering diagram image…"):
            img = render_to_bytesio(puml)
        if img:
            st.session_state["last_png"] = img.getvalue()  # store raw bytes
        else:
            st.session_state["last_png"] = None

    # ── Display results from session state (persists across reruns) ──
    if "last_puml" in st.session_state and st.session_state["last_puml"]:
        puml = st.session_state["last_puml"]
        diagram_name = st.session_state.get("last_diagram_name", "Diagram")
        png_bytes = st.session_state.get("last_png")
        safe_name = diagram_name.lower().replace(" ", "_")

        st.markdown(f"### 📊 {diagram_name}")
        if png_bytes:
            st.image(png_bytes, caption=diagram_name, use_container_width=True)

            # Download buttons — save directly to Downloads folder
            dl_col1, dl_col2, dl_col3 = st.columns(3)
            with dl_col1:
                if st.button("🖼️ Save as PNG", key="save_png"):
                    path = _save_file(png_bytes, f"{safe_name}.png")
                    st.success(f"✅ Saved to `{path}`")
            with dl_col2:
                if st.button("📷 Save as JPG", key="save_jpg"):
                    from PIL import Image
                    from io import BytesIO
                    img = Image.open(BytesIO(png_bytes)).convert("RGB")
                    jpg_buf = BytesIO()
                    img.save(jpg_buf, format="JPEG", quality=95)
                    path = _save_file(jpg_buf.getvalue(), f"{safe_name}.jpg")
                    st.success(f"✅ Saved to `{path}`")
            with dl_col3:
                if st.button("💾 Save Source", key="save_puml"):
                    path = _save_file(puml, f"{safe_name}.puml")
                    st.success(f"✅ Saved to `{path}`")
        else:
            st.error(
                "⚠️ **Rendering failed.** The diagram source could not be rendered. "
                "This may indicate a syntax issue that was not caught by validation. "
                "Review the source below and try **Regenerate**."
            )
            st.info(
                "💡 The diagram source is shown below. You can copy it and paste into "
                "[PlantUML Web](http://www.plantuml.com/plantuml/uml) to diagnose the issue."
            )

        with st.expander(
            "📝 View Diagram Source Code",
            expanded=not bool(png_bytes),
        ):
            st.code(puml, language="plantuml")

    # ── Batch diagram generation (parallel) ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("### ⚡ Batch Generate (Parallel)")
    st.caption(
        f"Generate multiple diagrams concurrently using "
        f"**{config.PARALLEL_MAX_WORKERS} worker threads**."
    )

    batch_selected = st.multiselect(
        "Select diagrams to generate:",
        diagram_names,
        default=["Class Diagram", "Component Diagram", "Use Case Diagram"],
        key="batch_select",
    )

    with st.popover("🚀 Batch Generate", disabled=len(batch_selected) == 0):
        status = _cached_ollama_status()
        models = status.get("models", [])
        if not models:
            models = [config.LLM_MODEL]
        selected_model_batch = st.selectbox("LLM Model (for all):", models, key="uml_batch_mod")
        btn_batch_col1, btn_batch_col2 = st.columns(2)
        with btn_batch_col1:
            if st.button("Generate Batch", key="gen_batch_uml_btn"):
                st.session_state["do_gen_batch_uml"] = selected_model_batch
                st.session_state["do_gen_batch_force"] = False
        with btn_batch_col2:
            if st.button("Regenerate Batch", key="regen_batch_uml_btn"):
                st.session_state["do_gen_batch_uml"] = selected_model_batch
                st.session_state["do_gen_batch_force"] = True

    batch_generated_now = False
    if st.session_state.get("do_gen_batch_uml"):
        selected_model = st.session_state.pop("do_gen_batch_uml")
        force_gen = st.session_state.pop("do_gen_batch_force", False)
        progress = st.progress(0, text=f"Starting batch generation ({selected_model})…")

        step_count = [0]
        total_steps = len(batch_selected)

        def _batch_progress(msg):
            step_count[0] += 1
            progress.progress(
                min(step_count[0] / total_steps, 1.0),
                text=msg,
            )

        # Build tasks — for batch, we skip focus class (use project-wide)
        tasks = []
        for name in batch_selected:
            gen_func, needs_focus = DIAGRAM_REGISTRY[name]
            if needs_focus:
                tasks.append((name, lambda f=gen_func: f(None, target_model=selected_model, force=force_gen)))
            else:
                tasks.append((name, lambda f=gen_func: f(target_model=selected_model, force=force_gen)))

        with st.spinner(f"Generating {len(tasks)} diagrams in parallel…"):
            results = run_parallel(
                tasks,
                max_workers=config.PARALLEL_MAX_WORKERS,
                progress_callback=_batch_progress,
            )

        progress.progress(1.0, text="✅ All diagrams generated!")

        # Pre-render all diagrams in parallel (faster than sequential HTTP)
        from concurrent.futures import ThreadPoolExecutor
        
        render_pairs = [(n, results[n]) for n in batch_selected if results.get(n)]
        with st.spinner(f"Rendering {len(render_pairs)} diagrams…"):
            with ThreadPoolExecutor(max_workers=4) as pool:
                rendered = dict(pool.map(_render_one, render_pairs))

        st.session_state["last_batch_order"] = list(batch_selected)
        st.session_state["last_batch_results"] = results
        st.session_state["last_batch_images"] = {
            name: (img.getvalue() if img else None)
            for name, img in rendered.items()
        }
        batch_generated_now = True

        # Display each result
        for name in batch_selected:
            puml = results.get(name, "")
            if not puml:
                continue
            st.markdown(f'<div class="diagram-card"><h4>📐 {name}</h4></div>',
                        unsafe_allow_html=True)

            img = rendered.get(name)
            if img:
                st.image(img, caption=name, use_container_width=True)
                img.seek(0)
                safe_name = name.lower().replace(" ", "_")
                st.download_button(
                    f"🖼️ Download {name} PNG", img.read(),
                    file_name=f"{safe_name}.png",
                    mime="image/png", key=f"dl_batch_{safe_name}_png",
                )
            else:
                st.error(
                    f"⚠️ Could not render {name}. The LLM-generated diagram "
                    f"may have syntax issues. See source below."
                )

            with st.expander(f"📝 {name} — Source", expanded=False):
                st.code(puml, language="plantuml")

    if (not batch_generated_now
            and st.session_state.get("last_batch_results")
            and st.session_state.get("last_batch_order")):
        batch_results = st.session_state["last_batch_results"]
        batch_images = st.session_state.get("last_batch_images", {})
        for name in st.session_state["last_batch_order"]:
            puml = batch_results.get(name, "")
            if not puml:
                continue
            st.markdown(f'<div class="diagram-card"><h4>{name}</h4></div>',
                        unsafe_allow_html=True)

            png_bytes = batch_images.get(name)
            if png_bytes:
                st.image(png_bytes, caption=name, use_container_width=True)
                safe_name = name.lower().replace(" ", "_")
                st.download_button(
                    f"Download {name} PNG", png_bytes,
                    file_name=f"{safe_name}.png",
                    mime="image/png", key=f"dl_batch_saved_{safe_name}_png",
                )
            else:
                st.error(
                    f"Could not render {name}. The LLM-generated diagram "
                    f"may have syntax issues. See source below."
                )

            with st.expander(f"{name} - Source", expanded=False):
                st.code(puml, language="plantuml")
