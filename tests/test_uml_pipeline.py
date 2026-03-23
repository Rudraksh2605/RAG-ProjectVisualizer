"""
Offline unit tests for the UML IR pipeline.

Tests IR parsing, validation, and compilation for all diagram types.
Does NOT require Ollama / Kroki — runs fully offline.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import unittest

from generators.uml_ir import parse_ir, IR_CLASSES
from generators.uml_compiler import compile_ir
from generators.uml_validator import validate_ir, validate_compiled_plantuml
from generators.uml_prompts import IR_SCHEMAS, IR_TASK_INSTRUCTIONS


# ═══════════════════════════════════════════════════════════════
#  Sample IR data for each diagram type
# ═══════════════════════════════════════════════════════════════

SAMPLE_DATA = {
    "class_diagram": {
        "title": "Test Class Diagram",
        "classes": [
            {"name": "User", "stereotype": "Entity", "package": "Domain",
             "fields": [{"name": "id", "type": "int"}, {"name": "name", "type": "String"}],
             "methods": [{"name": "login", "return_type": "boolean", "params": "email, pwd"}]},
            {"name": "UserRepo", "stereotype": "Repository", "package": "Data",
             "fields": [{"name": "db", "type": "Database"}],
             "methods": [{"name": "findById", "return_type": "User", "params": "id"}]},
        ],
        "relationships": [
            {"source": "UserRepo", "target": "User", "label": "manages", "arrow_type": "-->"},
        ],
    },
    "usecase_diagram": {
        "title": "Test Use Cases",
        "system_name": "MyApp",
        "actors": [{"name": "Student", "alias": "U"}],
        "usecases": [
            {"name": "Login", "alias": "UC1"},
            {"name": "Take Quiz", "alias": "UC2"},
        ],
        "relationships": [
            {"source": "Student", "target": "Login", "arrow_type": "-->"},
            {"source": "Student", "target": "Take Quiz", "arrow_type": "-->"},
        ],
    },
    "sequence_diagram": {
        "title": "Login Flow",
        "participants": [
            {"name": "LoginActivity", "participant_type": "participant"},
            {"name": "AuthService", "participant_type": "participant"},
            {"name": "UserDB", "participant_type": "database"},
        ],
        "messages": [
            {"sender": "LoginActivity", "receiver": "AuthService", "label": "1. login(email, pwd)", "activate": True},
            {"sender": "AuthService", "receiver": "UserDB", "label": "2. findUser(email)"},
            {"sender": "UserDB", "receiver": "AuthService", "label": "3. User object", "is_return": True},
            {"sender": "AuthService", "receiver": "LoginActivity", "label": "4. AuthResult", "is_return": True, "deactivate": True},
        ],
    },
    "activity_diagram": {
        "title": "Main Flow",
        "swimlanes": ["User", "App"],
        "steps": [
            {"step_type": "action", "label": "Open App", "swimlane": "User"},
            {"step_type": "decision", "condition": "Logged in?",
             "yes_steps": [{"step_type": "action", "label": "Show Dashboard"}],
             "no_steps": [{"step_type": "action", "label": "Show Login"}]},
            {"step_type": "action", "label": "Navigate to Feature", "swimlane": "App"},
            {"step_type": "stop"},
        ],
    },
    "state_diagram": {
        "title": "Activity Lifecycle",
        "states": [
            {"name": "Created", "display_name": "Created", "entry_action": "onCreate()"},
            {"name": "Started", "display_name": "Started"},
            {"name": "Resumed", "display_name": "Resumed"},
        ],
        "transitions": [
            {"source": "[*]", "target": "Created", "label": "launch"},
            {"source": "Created", "target": "Started", "label": "onStart"},
            {"source": "Started", "target": "Resumed", "label": "onResume"},
            {"source": "Resumed", "target": "[*]", "label": "finish"},
        ],
    },
    "component_diagram": {
        "title": "App Components",
        "components": [
            {"name": "LoginView", "stereotype": "Activity", "package": "UI"},
            {"name": "AuthRepo", "stereotype": "Repository", "package": "Data"},
        ],
        "interfaces": [{"name": "IAuth"}],
        "relationships": [
            {"source": "LoginView", "target": "IAuth", "label": "uses", "arrow_type": "-->"},
            {"source": "AuthRepo", "target": "IAuth", "label": "implements", "arrow_type": "..|>"},
        ],
    },
    "package_diagram": {
        "title": "Architecture Layers",
        "packages": [
            {"name": "UI", "classes": ["LoginActivity", "HomeActivity"]},
            {"name": "Domain", "classes": ["LoginUseCase"]},
            {"name": "Data", "classes": ["UserRepository"]},
        ],
        "relationships": [
            {"source": "UI", "target": "Domain", "label": "calls", "arrow_type": "-->"},
            {"source": "Domain", "target": "Data", "label": "depends on", "arrow_type": "-->"},
        ],
    },
    "deployment_diagram": {
        "title": "Deployment",
        "nodes": [
            {"name": "Android Device", "node_type": "node", "children": ["App", "SQLite"]},
            {"name": "Firebase", "node_type": "cloud", "children": ["Auth", "Firestore"]},
        ],
        "relationships": [
            {"source": "Android Device", "target": "Firebase", "label": "HTTPS", "arrow_type": "-->"},
        ],
    },
    "navigation_diagram": {
        "title": "App Navigation",
        "screens": [
            {"name": "SplashScreen", "display_name": "Splash"},
            {"name": "LoginScreen", "display_name": "Login"},
            {"name": "HomeScreen", "display_name": "Home"},
        ],
        "entry_screen": "SplashScreen",
        "exit_screens": ["HomeScreen"],
        "transitions": [
            {"source": "SplashScreen", "target": "LoginScreen", "label": "auto"},
            {"source": "LoginScreen", "target": "HomeScreen", "label": "login success"},
        ],
    },
}


class TestIRParsing(unittest.TestCase):
    """Test that all IR types can be parsed from dict without errors."""

    def test_all_types_parseable(self):
        for dtype, data in SAMPLE_DATA.items():
            with self.subTest(diagram_type=dtype):
                ir = parse_ir(dtype, data)
                self.assertIsNotNone(ir)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            parse_ir("unknown_diagram", {})

    def test_graceful_defaults(self):
        """Parse with minimal/empty data — should not crash."""
        ir = parse_ir("class_diagram", {"classes": [{"name": "A"}]})
        self.assertEqual(ir.classes[0].name, "A")
        self.assertEqual(ir.classes[0].fields, [])


class TestIRValidation(unittest.TestCase):
    """Test IR validators catch errors and accept valid data."""

    def test_all_valid_samples_pass(self):
        for dtype, data in SAMPLE_DATA.items():
            with self.subTest(diagram_type=dtype):
                ir = parse_ir(dtype, data)
                is_valid, errors = validate_ir(dtype, ir)
                self.assertTrue(is_valid, f"{dtype} failed: {errors}")

    def test_class_diagram_no_classes(self):
        ir = parse_ir("class_diagram", {"classes": []})
        valid, errors = validate_ir("class_diagram", ir)
        self.assertFalse(valid)
        self.assertTrue(any("No classes" in e for e in errors))

    def test_class_diagram_dangling_ref(self):
        data = {
            "classes": [{"name": "A"}],
            "relationships": [{"source": "A", "target": "B", "arrow_type": "-->"}],
        }
        ir = parse_ir("class_diagram", data)
        valid, errors = validate_ir("class_diagram", ir)
        self.assertFalse(valid)
        self.assertTrue(any("not in declared" in e for e in errors))

    def test_sequence_no_participants(self):
        ir = parse_ir("sequence_diagram", {"participants": []})
        valid, errors = validate_ir("sequence_diagram", ir)
        self.assertFalse(valid)

    def test_activity_empty_steps(self):
        ir = parse_ir("activity_diagram", {"steps": []})
        valid, errors = validate_ir("activity_diagram", ir)
        self.assertFalse(valid)

    def test_usecase_no_actors(self):
        ir = parse_ir("usecase_diagram", {"actors": [], "usecases": [{"name": "Login"}]})
        valid, errors = validate_ir("usecase_diagram", ir)
        self.assertFalse(valid)


class TestCompilation(unittest.TestCase):
    """Test that all IR types compile to valid PlantUML."""

    def test_all_types_compile(self):
        for dtype, data in SAMPLE_DATA.items():
            with self.subTest(diagram_type=dtype):
                ir = parse_ir(dtype, data)
                puml = compile_ir(dtype, ir)
                self.assertIn("@startuml", puml)
                self.assertIn("@enduml", puml)

    def test_class_diagram_content(self):
        ir = parse_ir("class_diagram", SAMPLE_DATA["class_diagram"])
        puml = compile_ir("class_diagram", ir)
        self.assertIn("class", puml)
        self.assertIn("User", puml)
        self.assertIn("UserRepo", puml)
        self.assertIn("manages", puml)

    def test_sequence_diagram_content(self):
        ir = parse_ir("sequence_diagram", SAMPLE_DATA["sequence_diagram"])
        puml = compile_ir("sequence_diagram", ir)
        self.assertIn("participant", puml.lower() + " " + puml)
        self.assertIn("LoginActivity", puml)
        self.assertIn("activate", puml)

    def test_activity_diagram_has_start_stop(self):
        ir = parse_ir("activity_diagram", SAMPLE_DATA["activity_diagram"])
        puml = compile_ir("activity_diagram", ir)
        self.assertIn("start", puml)
        self.assertIn("if (", puml)

    def test_navigation_has_state_syntax(self):
        ir = parse_ir("navigation_diagram", SAMPLE_DATA["navigation_diagram"])
        puml = compile_ir("navigation_diagram", ir)
        self.assertIn("state", puml)
        self.assertIn("[*]", puml)


class TestPostCompileValidation(unittest.TestCase):
    """Test post-compile PlantUML validator."""

    def test_all_compiled_pass_validation(self):
        for dtype, data in SAMPLE_DATA.items():
            with self.subTest(diagram_type=dtype):
                ir = parse_ir(dtype, data)
                puml = compile_ir(dtype, ir)
                valid, errors = validate_compiled_plantuml(puml, dtype)
                self.assertTrue(valid, f"{dtype}: {errors}")

    def test_empty_code_fails(self):
        valid, errors = validate_compiled_plantuml("")
        self.assertFalse(valid)

    def test_missing_startuml_fails(self):
        valid, errors = validate_compiled_plantuml("class Foo {}")
        self.assertFalse(valid)

    def test_leaked_thinking_detected(self):
        code = "@startuml\n<thinking>Let me think</thinking>\nclass Foo\n@enduml"
        valid, errors = validate_compiled_plantuml(code)
        self.assertFalse(valid)
        self.assertTrue(any("Leaked" in e for e in errors))

    def test_unbalanced_braces_detected(self):
        code = "@startuml\nclass Foo {\n@enduml"
        valid, errors = validate_compiled_plantuml(code)
        self.assertFalse(valid)
        self.assertTrue(any("Unbalanced" in e for e in errors))


class TestJSONExtraction(unittest.TestCase):
    """Test JSON extraction from LLM output."""

    def test_clean_json(self):
        from generators.plantuml_gen import _extract_json
        data = _extract_json('{"title": "Test", "classes": []}')
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Test")

    def test_json_in_markdown_fence(self):
        from generators.plantuml_gen import _extract_json
        raw = '```json\n{"title": "Test"}\n```'
        data = _extract_json(raw)
        self.assertIsNotNone(data)

    def test_json_with_preamble(self):
        from generators.plantuml_gen import _extract_json
        raw = 'Here is the JSON:\n{"title": "Hello"}\nHope this helps!'
        data = _extract_json(raw)
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Hello")

    def test_trailing_comma_fix(self):
        from generators.plantuml_gen import _extract_json
        raw = '{"title": "Test", "classes": [],}'
        data = _extract_json(raw)
        self.assertIsNotNone(data)

    def test_no_json_returns_none(self):
        from generators.plantuml_gen import _extract_json
        self.assertIsNone(_extract_json("No JSON here"))
        self.assertIsNone(_extract_json(""))


class TestPromptSchemas(unittest.TestCase):
    """Test that all diagram types have prompt schemas and instructions."""

    def test_all_types_have_schemas(self):
        for dtype in IR_CLASSES:
            with self.subTest(dtype=dtype):
                self.assertIn(dtype, IR_SCHEMAS)
                self.assertTrue(len(IR_SCHEMAS[dtype]) > 50)

    def test_all_types_have_instructions(self):
        for dtype in IR_CLASSES:
            with self.subTest(dtype=dtype):
                self.assertIn(dtype, IR_TASK_INSTRUCTIONS)
                self.assertTrue(len(IR_TASK_INSTRUCTIONS[dtype]) > 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
