import sys
sys.path.append("d:\\GitHub\\RAG-ProjectVisualizer")
from generators.plantuml_gen import _test_render_kroki

code4 = """
@startuml
[*] --> LauncherActivity
LauncherActivity --> LogInButton
@enduml
"""

renderable, error = _test_render_kroki(code4)
print(f"Test 4 - No quotes, no spaces: {renderable}")
