"""
Unit tests for PlantUML extraction, validation, and repair logic.
These are pure functions — no LLM or RAG access needed.

Run:  python -m pytest test_plantuml.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.plantuml_gen import (
    _extract_plantuml,
    _validate_plantuml,
    _repair_plantuml,
    _inject_skinparam,
    DIAGRAM_SPECS,
    DIAGRAM_REGISTRY,
)

# ═══════════════════════════════════════════════════════════════
#  Tests for _extract_plantuml
# ═══════════════════════════════════════════════════════════════

class TestExtractPlantUML:
    """Tests for extracting PlantUML from raw LLM output."""

    def test_clean_block(self):
        raw = "@startuml\nclass Foo\n@enduml"
        assert _extract_plantuml(raw) == raw

    def test_block_with_surrounding_text(self):
        raw = "Here is the diagram:\n@startuml\nclass Foo\n@enduml\nHope this helps!"
        result = _extract_plantuml(raw)
        assert result.startswith("@startuml")
        assert result.endswith("@enduml")
        assert "class Foo" in result

    def test_code_fence_plantuml(self):
        raw = "```plantuml\nclass Bar\nclass Baz\n```"
        result = _extract_plantuml(raw)
        assert "@startuml" in result
        assert "class Bar" in result

    def test_code_fence_with_startuml_inside(self):
        raw = "```plantuml\n@startuml\nclass Foo\n@enduml\n```"
        result = _extract_plantuml(raw)
        assert result.strip() == "@startuml\nclass Foo\n@enduml"

    def test_empty_input(self):
        result = _extract_plantuml("")
        assert "@startuml" in result
        assert "@enduml" in result

    def test_none_input(self):
        result = _extract_plantuml(None)
        assert "@startuml" in result

    def test_error_marker_detection(self):
        raw = "[Ollama error] connection refused"
        result = _extract_plantuml(raw)
        assert "LLM could not generate" in result

    def test_apology_marker(self):
        raw = "I'm sorry, I cannot generate a diagram for this."
        result = _extract_plantuml(raw)
        assert "LLM could not generate" in result

    def test_multiple_blocks_picks_longest(self):
        raw = "@startuml\nA\n@enduml\n\n@startuml\nclass Foo\nclass Bar\n@enduml"
        result = _extract_plantuml(raw)
        assert "class Foo" in result
        assert "class Bar" in result

    def test_strips_chat_prefix(self):
        raw = "Sure, here's the diagram:\nclass Alpha\nclass Beta"
        result = _extract_plantuml(raw)
        assert "@startuml" in result
        assert "class Alpha" in result


# ═══════════════════════════════════════════════════════════════
#  Tests for _validate_plantuml
# ═══════════════════════════════════════════════════════════════

class TestValidatePlantUML:
    """Tests for PlantUML validation."""

    def test_valid_class_diagram(self):
        code = "@startuml\nclass Foo {\n  +bar()\n}\n@enduml"
        is_valid, err = _validate_plantuml(code, "class_diagram")
        assert is_valid, err

    def test_missing_startuml(self):
        is_valid, err = _validate_plantuml("class Foo {\n  +bar()\n}\n@enduml")
        assert not is_valid
        assert "Missing @startuml" in err

    def test_missing_enduml(self):
        is_valid, err = _validate_plantuml("@startuml\nclass Foo {\n  +bar()\n}")
        assert not is_valid
        assert "Missing @enduml" in err

    def test_empty_body(self):
        is_valid, err = _validate_plantuml("@startuml\n' just a comment\n@enduml")
        assert not is_valid
        assert "empty" in err.lower()

    def test_unbalanced_braces(self):
        code = "@startuml\nclass Foo {\n  +bar()\n@enduml"
        is_valid, err = _validate_plantuml(code)
        assert not is_valid
        assert "Unbalanced" in err

    def test_too_short(self):
        is_valid, err = _validate_plantuml("short")
        assert not is_valid

    def test_type_specific_class_valid(self):
        code = "@startuml\nclass Foo\nclass Bar\nFoo --> Bar\n@enduml"
        is_valid, _ = _validate_plantuml(code, "class_diagram")
        assert is_valid

    def test_type_specific_class_missing_keyword(self):
        code = "@startuml\ntitle \"Hello\"\nnote \"something here\"\n@enduml"
        is_valid, err = _validate_plantuml(code, "class_diagram")
        assert not is_valid
        assert "class_diagram" in err

    def test_type_specific_sequence_valid(self):
        code = "@startuml\nparticipant A\nA -> B : hello\n@enduml"
        is_valid, _ = _validate_plantuml(code, "sequence_diagram")
        assert is_valid

    def test_type_specific_state_valid(self):
        code = "@startuml\n[*] --> Idle\nstate Idle\n@enduml"
        is_valid, _ = _validate_plantuml(code, "state_diagram")
        assert is_valid

    def test_error_marker_in_body(self):
        code = "@startuml\nI'm sorry I cannot help\n@enduml"
        is_valid, err = _validate_plantuml(code)
        assert not is_valid
        assert "error message" in err.lower()


# ═══════════════════════════════════════════════════════════════
#  Tests for _repair_plantuml
# ═══════════════════════════════════════════════════════════════

class TestRepairPlantUML:
    """Tests for automatic PlantUML repair."""

    def test_adds_missing_startuml(self):
        code = "class Foo\n@enduml"
        result = _repair_plantuml(code)
        assert result.startswith("@startuml")

    def test_adds_missing_enduml(self):
        code = "@startuml\nclass Foo"
        result = _repair_plantuml(code)
        assert result.rstrip().endswith("@enduml")

    def test_fixes_kotlin_inheritance(self):
        code = "@startuml\nclass Child : Parent\n@enduml"
        result = _repair_plantuml(code)
        assert "extends" in result
        assert ":" not in result.split("class")[1].split("\n")[0]

    def test_fixes_unbalanced_braces(self):
        code = "@startuml\nclass Foo {\n  +bar()\n@enduml"
        result = _repair_plantuml(code)
        assert result.count("{") == result.count("}")

    def test_removes_markdown_backticks(self):
        code = "@startuml\n```class Foo```\n@enduml"
        result = _repair_plantuml(code)
        assert "```" not in result

    def test_removes_commentary_lines(self):
        code = "@startuml\nHere is the diagram\nclass Foo\n@enduml"
        result = _repair_plantuml(code)
        assert "Here is" not in result
        assert "class Foo" in result

    def test_removes_html_tags(self):
        code = "@startuml\nclass <b>Foo</b>\n@enduml"
        result = _repair_plantuml(code)
        assert "<b>" not in result
        assert "Foo" in result

    def test_fixes_duplicate_startuml(self):
        code = "@startuml\n@startuml\nclass Foo\n@enduml"
        result = _repair_plantuml(code)
        assert result.count("@startuml") == 1

    def test_fixes_duplicate_enduml(self):
        code = "@startuml\nclass Foo\n@enduml\n@enduml"
        result = _repair_plantuml(code)
        assert result.count("@enduml") == 1

    def test_fixes_missing_deactivate(self):
        code = "@startuml\nA -> B : msg\nactivate B\n@enduml"
        result = _repair_plantuml(code)
        assert "deactivate" in result

    def test_fixes_unclosed_alt(self):
        code = "@startuml\nalt success\nA -> B : ok\n@enduml"
        result = _repair_plantuml(code)
        end_count = len([l for l in result.split("\n") if l.strip() == "end"])
        assert end_count >= 1

    def test_note_inside_state_block(self):
        code = '@startuml\nstate "Active" as S1 { note right of S1 : info }\n@enduml'
        result = _repair_plantuml(code)
        # Note should be extracted from inside the block
        assert "note right of S1" in result

    def test_idempotent_on_valid_code(self):
        code = "@startuml\nclass Foo {\n  +bar()\n}\nFoo --> Bar\n@enduml"
        result = _repair_plantuml(code)
        assert "class Foo" in result
        assert "Foo --> Bar" in result


# ═══════════════════════════════════════════════════════════════
#  Tests for _inject_skinparam
# ═══════════════════════════════════════════════════════════════

class TestInjectSkinparam:
    """Tests for smart skinparam merging."""

    def test_injects_defaults_on_bare_diagram(self):
        code = "@startuml\nclass Foo\n@enduml"
        result = _inject_skinparam(code)
        assert "skinparam defaultFontName" in result
        assert "skinparam shadowing" in result

    def test_preserves_llm_overrides(self):
        code = "@startuml\nskinparam BackgroundColor #ffffff\nclass Foo\n@enduml"
        result = _inject_skinparam(code)
        # LLM's override should be used
        assert "#ffffff" in result

    def test_no_duplicate_simple_skinparams(self):
        code = "@startuml\nskinparam shadowing false\nclass Foo\n@enduml"
        result = _inject_skinparam(code)
        # Should not have two "skinparam shadowing" lines
        lines = [l for l in result.split("\n") if "skinparam shadowing" in l.lower()]
        assert len(lines) == 1


# ═══════════════════════════════════════════════════════════════
#  Tests for registry consistency
# ═══════════════════════════════════════════════════════════════

class TestRegistryConsistency:
    """Ensure DIAGRAM_SPECS and DIAGRAM_REGISTRY stay in sync."""

    def test_registry_has_all_specs(self):
        for key in DIAGRAM_SPECS:
            display = DIAGRAM_SPECS[key]["display_name"]
            assert display in DIAGRAM_REGISTRY, f"{display} missing from DIAGRAM_REGISTRY"

    def test_registry_entries_are_callable(self):
        for display_name, (func, _) in DIAGRAM_REGISTRY.items():
            assert callable(func), f"Registry entry '{display_name}' is not callable: {type(func)}"

    def test_all_specs_have_required_fields(self):
        for key, spec in DIAGRAM_SPECS.items():
            assert "display_name" in spec, f"{key} missing display_name"
            assert "query_default" in spec, f"{key} missing query_default"
            assert "top_k" in spec, f"{key} missing top_k"

    def test_focused_specs_have_query_focused(self):
        for key, spec in DIAGRAM_SPECS.items():
            if spec.get("has_focus"):
                assert "query_focused" in spec, f"{key} has has_focus=True but no query_focused"


# ═══════════════════════════════════════════════════════════════
#  Run with pytest or directly
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
