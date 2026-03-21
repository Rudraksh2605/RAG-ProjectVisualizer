import sys
sys.path.append("d:\\GitHub\\RAG-ProjectVisualizer")
from generators.plantuml_gen import _test_render_kroki

code = """
@startuml
[*] --> "Launcher Activity: Start"

"Launcher Activity: Start" --> LogInButton : LogInButton.setOnClickListener
@enduml
"""

renderable, error = _test_render_kroki(code)
print(f"Test 1 - Simple state: {renderable} | Error: {error}")

code2 = """
@startuml
[*] --> "Launcher Activity: Start"

"Launcher Activity: Start" --> LogInButton : LogInButton.setOnClickListener { startActivity(Intent(this, LogIn::class.java)) }
@enduml
"""
renderable, error = _test_render_kroki(code2)
print(f"Test 2 - With braces: {renderable} | Error: {error}")


code3 = """
@startuml
state "Launcher Activity: Start" as start
[*] --> start

start --> LogInButton : LogInButton.setOnClickListener { startActivity(Intent(this, LogIn::class.java)) }
@enduml
"""
renderable, error = _test_render_kroki(code3)
print(f"Test 3 - Explicit state: {renderable} | Error: {error}")

