"""
JSON schema descriptions for UML IR prompts.

Each diagram type has a text description of the expected JSON schema
that gets injected into the LLM prompt.  The LLM is asked to return
ONLY valid JSON matching this schema — no PlantUML, no markdown, no prose.
"""

# ═══════════════════════════════════════════════════════════════
#  Per-diagram JSON schema descriptions
# ═══════════════════════════════════════════════════════════════

IR_SCHEMAS = {
    "class_diagram": """{
  "title": "string — diagram title",
  "classes": [
    {
      "name": "string — class name (PascalCase, no spaces)",
      "stereotype": "string — e.g. Activity, ViewModel, Repository, Entity, Service (optional)",
      "is_abstract": false,
      "is_interface": false,
      "package": "string — architectural layer e.g. UI, Domain, Data (optional)",
      "fields": [
        {"name": "string", "type": "string", "visibility": "+|-|#"}
      ],
      "methods": [
        {"name": "string", "return_type": "string", "params": "string", "visibility": "+|-|#"}
      ]
    }
  ],
  "external_classes": [
    {
      "name": "string — external collaborator not defined in the project (e.g. FirebaseAuth, Retrofit)",
      "stereotype": "External"
    }
  ],
  "relationships": [
    {
      "source": "string — MUST match a class name or external_class name",
      "target": "string — MUST match a class name or external_class name",
      "label": "string — verb describing the relationship",
      "arrow_type": "-->|..|>|*--|--|<|--"
    }
  ],
  "notes": [
    {"target": "string — class name", "position": "right|left", "text": "string"}
  ]
}""",

    "usecase_diagram": """{
  "title": "string — diagram title",
  "system_name": "string — name of the system/app boundary",
  "actors": [
    {"name": "string — actor name", "alias": "string — optional short alias"}
  ],
  "usecases": [
    {"name": "string — verb+noun action e.g. 'Take Quiz'", "alias": "string — optional short alias"}
  ],
  "relationships": [
    {
      "source": "string — MUST match an actor or usecase name above",
      "target": "string — MUST match an actor or usecase name above",
      "label": "string — e.g. <<include>>, <<extend>>, or empty",
      "arrow_type": "-->|..>"
    }
  ],
  "notes": [
    {"target": "string — usecase name", "position": "right|left", "text": "string"}
  ]
}""",

    "sequence_diagram": """{
  "title": "string — diagram title describing the flow",
  "participants": [
    {
      "name": "string — full class/component name (e.g. LoginActivity, not LA)",
      "alias": "string — optional, metadata only, do NOT use in messages",
      "stereotype": "string — e.g. Activity, Service (optional)",
      "participant_type": "participant|actor|database|entity"
    }
  ],
  "messages": [
    {
      "sender": "string — MUST exactly match a participant NAME (not alias)",
      "receiver": "string — MUST exactly match a participant NAME (not alias)",
      "label": "string — numbered message e.g. '1. loginUser(email, pwd)'",
      "is_return": false,
      "activate": false,
      "deactivate": false
    }
  ],
  "groups": [
    {
      "group_type": "alt|opt|loop",
      "label": "string — condition label",
      "messages": ["same format as messages above — sender/receiver MUST match participant names"],
      "else_label": "string — else condition (optional)",
      "else_messages": ["same format as messages above"]
    }
  ],
  "notes": [
    {"target": "string — participant name", "position": "right|left", "text": "string"}
  ]
}""",

    "activity_diagram": """{
  "title": "string — diagram title",
  "swimlanes": ["string — swimlane names, e.g. 'User', 'App', 'Backend'"],
  "steps": [
    {
      "step_type": "action|decision|fork|join|stop",
      "label": "string — action description or empty for stop",
      "swimlane": "string — which swimlane this step belongs to (optional)",
      "condition": "string — for decisions only",
      "yes_steps": ["nested steps for yes branch"],
      "no_steps": ["nested steps for no branch"]
    }
  ],
  "notes": [
    {"target": "", "position": "right", "text": "string"}
  ]
}""",

    "state_diagram": """{
  "title": "string — diagram title",
  "states": [
    {
      "name": "string — unique state identifier (no spaces)",
      "display_name": "string — human-readable name",
      "entry_action": "string — entry / action (optional)",
      "exit_action": "string — exit / action (optional)",
      "do_action": "string — do / action (optional)"
    }
  ],
  "transitions": [
    {
      "source": "string — state name or '[*]' for initial/final",
      "target": "string — state name or '[*]' for initial/final",
      "label": "string — event name",
      "guard": "string — guard condition (optional)"
    }
  ],
  "notes": [
    {"target": "string — state name", "position": "right|left", "text": "string"}
  ]
}""",

    "component_diagram": """{
  "title": "string — diagram title",
  "components": [
    {
      "name": "string — component name",
      "stereotype": "string — e.g. Activity, Service, Repository (optional)",
      "package": "string — feature group (optional)"
    }
  ],
  "external_components": [
    {
      "name": "string — external library/framework component not in the project",
      "stereotype": "External"
    }
  ],
  "interfaces": [
    {"name": "string — interface name", "alias": "string — optional"}
  ],
  "relationships": [
    {
      "source": "string — MUST match a component, external_component, or interface name",
      "target": "string — MUST match a component, external_component, or interface name",
      "label": "string — interaction type",
      "arrow_type": "-->|..>"
    }
  ],
  "notes": [
    {"target": "string", "position": "right|left", "text": "string"}
  ]
}""",

    "package_diagram": """{
  "title": "string — diagram title",
  "packages": [
    {
      "name": "string — layer/package name e.g. UI, Domain, Data",
      "classes": ["string — 2-3 key class names in this package"]
    }
  ],
  "relationships": [
    {
      "source": "string — class or package name",
      "target": "string — class or package name",
      "label": "string — dependency type e.g. 'calls', 'depends on'",
      "arrow_type": "-->|..>"
    }
  ],
  "notes": [
    {"target": "", "position": "right", "text": "string"}
  ]
}""",

    "deployment_diagram": """{
  "title": "string — diagram title",
  "nodes": [
    {
      "name": "string — node name e.g. 'Android Device', 'Firebase'",
      "node_type": "node|database|cloud|artifact",
      "children": [
        {
          "name": "string — child artifact/component name",
          "child_type": "artifact|component|database"
        }
      ]
    }
  ],
  "relationships": [
    {
      "source": "string — MUST match a node name OR a child name above",
      "target": "string — MUST match a node name OR a child name above",
      "label": "string — protocol e.g. 'HTTPS', 'REST API'",
      "arrow_type": "-->"
    }
  ],
  "notes": [
    {"target": "string — node or child name", "position": "right|left", "text": "string"}
  ]
}""",

    "navigation_diagram": """{
  "title": "string — diagram title",
  "screens": [
    {
      "name": "string — screen identifier matching Activity/Fragment class name (e.g. LoginActivity)",
      "display_name": "string — human-readable name e.g. 'Login'"
    }
  ],
  "entry_screen": "string — name of the launcher/first screen",
  "exit_screens": ["string — names of screens that can exit the app"],
  "transitions": [
    {
      "source": "string — screen name or '[*]'",
      "target": "string — screen name or '[*]'",
      "label": "string — user action that triggers navigation",
      "guard": "string — optional condition"
    }
  ],
  "notes": [
    {"target": "string — screen name", "position": "right|left", "text": "string"}
  ]
}""",
}


# ═══════════════════════════════════════════════════════════════
#  Task-specific instructions for the LLM
# ═══════════════════════════════════════════════════════════════

IR_TASK_INSTRUCTIONS = {
    "class_diagram": (
        "Analyze the code context and identify the 4-6 MOST IMPORTANT classes "
        "(core domain, not utility classes). For each class include: name, "
        "stereotype (Activity/ViewModel/Repository/Entity/Service), package/layer, "
        "2-3 key fields, and 2-4 public methods (skip getters/setters). "
        "Include relationships showing inheritance (--|>), implementation (..|>), "
        "composition (*--), and dependency (..>). Label every relationship with a verb. "
        "If a relationship endpoint is a library/framework class not in the project "
        "(e.g. FirebaseAuth, Retrofit), list it under external_classes."
    ),
    "usecase_diagram": (
        "Identify the distinct business features and user capabilities in this app. "
        "Define 1-2 actors. Name use cases as VERB+NOUN actions (e.g. 'Take Quiz', "
        "'Edit Profile'), NOT screen names. Show <<include>> for mandatory sub-steps "
        "and <<extend>> for optional expansions. Group all use cases under the system boundary."
    ),
    "sequence_diagram": (
        "Trace ONE complete user interaction flow (e.g. login, main feature) from "
        "start to finish. Use at most 4-5 participants. Number each message for "
        "readability. Show ONE request-response round-trip. Use groups (alt/opt) "
        "for ONE key decision point. "
        "CRITICAL: sender and receiver in messages MUST be the FULL participant name "
        "(e.g. 'LoginActivity', not 'LA'). Do NOT use aliases or abbreviations in "
        "sender/receiver fields. Aliases are optional metadata only."
    ),
    "activity_diagram": (
        "Show ONE primary user flow from app launch to the main feature. "
        "Use 2-3 swimlanes (User, App, Backend). Include 8-12 steps max. "
        "Include at least one decision point. Steps should be concrete actions."
    ),
    "state_diagram": (
        "Show the lifecycle of ONE key component (Activity or Fragment). "
        "Limit to 5-7 states. Include entry/exit actions for important states. "
        "Label every transition with the event and guard condition."
    ),
    "component_diagram": (
        "Show how the app's major components connect. Group into 2-4 feature "
        "packages. Add stereotypes (Activity/Service/Repository). Label every "
        "connection with the interaction type. Limit to 6-10 components. "
        "If a relationship references a library/framework component not in the project, "
        "list it under external_components."
    ),
    "package_diagram": (
        "Show the 3-4 architectural layers with 2-3 key classes in each. "
        "Label every dependency arrow with the relationship type."
    ),
    "deployment_diagram": (
        "Show where the app runs and what external services it connects to. "
        "Include the Android device, servers, databases, and cloud services. "
        "Label connections with protocol. Limit to 4-6 nodes. "
        "Children inside nodes should be structured with name and child_type. "
        "Relationships may target either node names or child names."
    ),
    "navigation_diagram": (
        "Map the app's navigation flow. Screens will be auto-detected from the "
        "codebase (Activities and Fragments). Your job is to define the transitions "
        "between screens, user actions that trigger them, and the entry/exit screens. "
        "Use the EXACT Activity/Fragment class names from the code as screen names. "
        "Include the launcher (entry) screen and exit points. "
        "Label every transition with the user action that triggers it."
    ),
}
