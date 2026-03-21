import sys
sys.path.append("d:\\GitHub\\RAG-ProjectVisualizer")
from generators.plantuml_gen import _test_render_kroki

code = """
@startuml
[*] --> "Launcher Activity: Start"

"Launcher Activity: Start" --> LogInButton : LogInButton.setOnClickListener { startActivity(Intent(this, LogIn::class.java)) }
"Launcher Activity: Start" --> signUpButton : signUpButton.setOnClickListener { startActivity(Intent(this, SignUp::class.java)) }

LogInButton --> "Activity: LogIn"
signUpButton --> "Activity: SignUp"

"Activity: LogIn" --> googleButton : googleButton.setOnClickListener { signIn() }
"Activity: LogIn" --> loginButton : loginButton.setOnClickListener { login(email, password) }

"Activity: SignUp" --> googleButton : googleButton.setOnClickListener { signIn() }
"Activity: SignUp" --> signUpButton : signUpButton.setOnClickListener { signUp(email, password) }

"Activity: Home" --> btn_article : btn_article.setOnClickListener { startActivity(Intent(this, ArticlesListActivity::class.java)) }
"Activity: Home" --> btn_home : btn_home.setOnClickListener { startActivity(Intent(this, Home::class.java)) }
"Activity: Home" --> btn_scanner : btn_scanner.setOnClickListener { startActivityForResult(Intent(MediaStore.ACTION_IMAGE_CAPTURE), CAMERA_REQUEST_CODE) }
"Activity: Home" --> btn_event : btn_event.setOnClickListener { startActivity(Intent(this, EventsActivity::class.java)) }
"Activity: Home" --> btn_chat_bot : btn_chat_bot.setOnClickListener { startActivity(Intent(this, ChatBotActivity::class.java)) }

ArticlesListActivity --> btn_article : btn_article.setOnClickListener { startActivity(Intent(this, ArticlesListActivity::class.java)) }
ArticlesListActivity --> btn_home : btn_home.setOnClickListener { startActivity(Intent(this, Home::class.java)) }
ArticlesListActivity --> btn_scanner : btn_scanner.setOnClickListener { startActivityForResult(Intent(MediaStore.ACTION_IMAGE_CAPTURE), CAMERA_REQUEST_CODE) }
ArticlesListActivity --> btn_event : btn_event.setOnClickListener { startActivity(Intent(this, EventsActivity::class.java)) }
ArticlesListActivity --> btn_chat_bot : btn_chat_bot.setOnClickListener { startActivity(Intent(this, ChatBotActivity::class.java)) }

EventsActivity --> btn_article : btn_article.setOnClickListener { startActivity(Intent(this, ArticlesListActivity::class.java)) }
EventsActivity --> btn_home : btn_home.setOnClickListener { startActivity(Intent(this, Home::class.java)) }
EventsActivity --> btn_scanner : btn_scanner.setOnClickListener { startActivityForResult(Intent(MediaStore.ACTION_IMAGE_CAPTURE), CAMERA_REQUEST_CODE) }
EventsActivity --> btn_event : btn_event.setOnClickListener { startActivity(Intent(this, EventsActivity::class.java)) }
EventsActivity --> btn_chat_bot : btn_chat_bot.setOnClickListener { startActivity(Intent(this, ChatBotActivity::class.java)) }

ChatBotActivity --> [*] : None

[*] --> "Launcher Activity: Start"
@enduml
"""

renderable, error = _test_render_kroki(code)
print(f"Renderable: {renderable}")
if not renderable:
    print(f"Error: {error}")
