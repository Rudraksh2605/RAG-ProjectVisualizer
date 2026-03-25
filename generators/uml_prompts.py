"""
JSON schema descriptions and modeling rules for UML IR prompts.

The LLM is asked to return ONLY valid JSON matching the selected IR schema.
This module also captures the semantic definition of each diagram type so the
model knows what kind of system view it is generating.
"""

IR_SCHEMAS = {
    "class_diagram": """{
  "title": "string - diagram title",
  "classes": [
    {
      "name": "string - class name (PascalCase, no spaces)",
      "stereotype": "string - e.g. Activity, ViewModel, Repository, Entity, Service (optional)",
      "is_abstract": false,
      "is_interface": false,
      "package": "string - architectural layer such as UI, Domain, Data (optional)",
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
      "name": "string - external collaborator not defined in the project (e.g. FirebaseAuth, Retrofit)",
      "stereotype": "External"
    }
  ],
  "relationships": [
    {
      "source": "string - MUST match a class name or external_class name",
      "target": "string - MUST match a class name or external_class name",
      "label": "string - verb describing the relationship",
      "arrow_type": "--|>|..|>|*--|..>|--"
    }
  ],
  "notes": [
    {"target": "string - class name", "position": "right|left", "text": "string"}
  ]
}""",
    "usecase_diagram": """{
  "title": "string - diagram title",
  "system_name": "string - name of the system/app boundary",
  "actors": [
    {"name": "string - actor name", "alias": "string - optional short alias"}
  ],
  "usecases": [
    {"name": "string - verb phrase such as 'Take Quiz' or 'Reset Password'", "alias": "string - optional short alias"}
  ],
  "relationships": [
    {
      "source": "string - MUST match an actor or usecase name above",
      "target": "string - MUST match an actor or usecase name above",
      "label": "string - empty, <<include>>, <<extend>>, or generalization label",
      "arrow_type": "-->|..>|--|>"
    }
  ],
  "notes": [
    {"target": "string - actor or usecase name", "position": "right|left", "text": "string"}
  ]
}""",
    "sequence_diagram": """{
  "title": "string - diagram title describing the scenario",
  "participants": [
    {
      "name": "string - full class/component/runtime participant name",
      "alias": "string - optional metadata only",
      "stereotype": "string - e.g. Activity, Service, Repository (optional)",
      "participant_type": "participant|actor|database|entity"
    }
  ],
  "messages": [
    {
      "sender": "string - MUST exactly match a participant NAME",
      "receiver": "string - MUST exactly match a participant NAME",
      "label": "string - concrete message or call such as '1. submitLogin(email, password)'",
      "is_return": false,
      "activate": false,
      "deactivate": false
    }
  ],
  "groups": [
    {
      "group_type": "alt|opt|loop",
      "label": "string - condition or loop label",
      "messages": ["same format as messages above"],
      "else_label": "string - else condition (optional, alt only)",
      "else_messages": ["same format as messages above"]
    }
  ],
  "notes": [
    {"target": "string - participant name", "position": "right|left", "text": "string"}
  ]
}""",
    "activity_diagram": """{
  "title": "string - diagram title",
  "swimlanes": ["string - swimlane names such as 'User', 'App', 'Backend'"],
  "steps": [
    {
      "step_type": "action|decision|fork|join|stop",
      "label": "string - action description or empty for stop",
      "swimlane": "string - swimlane this step belongs to (optional)",
      "condition": "string - for decisions only",
      "yes_steps": ["nested steps for yes branch"],
      "no_steps": ["nested steps for no branch"]
    }
  ],
  "notes": [
    {"target": "", "position": "right", "text": "string"}
  ]
}""",
    "state_diagram": """{
  "title": "string - diagram title",
  "states": [
    {
      "name": "string - unique state identifier",
      "display_name": "string - human-readable state label",
      "entry_action": "string - entry action (optional)",
      "exit_action": "string - exit action (optional)",
      "do_action": "string - ongoing action (optional)"
    }
  ],
  "transitions": [
    {
      "source": "string - state name or '[*]' for initial/final",
      "target": "string - state name or '[*]' for initial/final",
      "label": "string - event name",
      "guard": "string - guard condition (optional)"
    }
  ],
  "notes": [
    {"target": "string - state name", "position": "right|left", "text": "string"}
  ]
}""",
    "component_diagram": """{
  "title": "string - diagram title",
  "components": [
    {
      "name": "string - component name",
      "stereotype": "string - e.g. Activity, Service, Repository (optional)",
      "package": "string - feature group or subsystem (optional)"
    }
  ],
  "external_components": [
    {
      "name": "string - external library/framework/service",
      "stereotype": "External"
    }
  ],
  "interfaces": [
    {"name": "string - interface name", "alias": "string - optional"}
  ],
  "relationships": [
    {
      "source": "string - MUST match a component, external_component, or interface name",
      "target": "string - MUST match a component, external_component, or interface name",
      "label": "string - dependency or integration type",
      "arrow_type": "-->|..>|--"
    }
  ],
  "notes": [
    {"target": "string", "position": "right|left", "text": "string"}
  ]
}""",
    "package_diagram": """{
  "title": "string - diagram title",
  "packages": [
    {
      "name": "string - package/layer name such as UI, Domain, Data",
      "classes": ["string - 2-3 representative class names in this package"]
    }
  ],
  "relationships": [
    {
      "source": "string - package name or class name declared above",
      "target": "string - package name or class name declared above",
      "label": "string - dependency type such as 'depends on' or 'uses'",
      "arrow_type": "-->|..>|--"
    }
  ],
  "notes": [
    {"target": "string - optional package or class name", "position": "right|left", "text": "string"}
  ]
}""",
    "deployment_diagram": """{
  "title": "string - diagram title",
  "nodes": [
    {
      "name": "string - runtime node name such as 'Android Device' or 'Firebase'",
      "node_type": "node|database|cloud|artifact",
      "children": [
        {
          "name": "string - deployed artifact/component/database inside the node",
          "child_type": "artifact|component|database"
        }
      ]
    }
  ],
  "relationships": [
    {
      "source": "string - MUST match a node name or child name above",
      "target": "string - MUST match a node name or child name above",
      "label": "string - protocol or communication type such as HTTPS, REST, SQL",
      "arrow_type": "-->"
    }
  ],
  "notes": [
    {"target": "string - node or child name", "position": "right|left", "text": "string"}
  ]
}""",
    "navigation_diagram": """{
  "title": "string - diagram title",
  "screens": [
    {
      "name": "string - screen identifier matching Activity/Fragment class name",
      "display_name": "string - human-readable label"
    }
  ],
  "entry_screen": "string - launcher or first screen name",
  "exit_screens": ["string - names of screens that can leave the app flow"],
  "transitions": [
    {
      "source": "string - screen name or '[*]'",
      "target": "string - screen name or '[*]'",
      "label": "string - user/system action that triggers navigation",
      "guard": "string - optional condition"
    }
  ],
  "notes": [
    {"target": "string - screen name", "position": "right|left", "text": "string"}
  ]
}""",
}


IR_DIAGRAM_RULES = {
    "class_diagram": (
        "A class diagram is a static structural view of the codebase. It shows the main "
        "classes or interfaces, their responsibilities, important attributes and methods, "
        "and how those types depend on or inherit from one another.\n"
        "Required content:\n"
        "- Show only important domain or architecture classes, not random helpers or trivial utilities.\n"
        "- Include class names, meaningful public methods, and important fields.\n"
        "- Use inheritance, implementation, composition, and dependency relationships only when supported by the code context.\n"
        "Do not show:\n"
        "- Runtime call order, user goals, UI screen navigation, or deployment nodes.\n"
        "- Generic placeholders such as Helper, Manager, or Utils unless the code context proves they are central."
    ),
    "usecase_diagram": (
        "A use case diagram is a user-goal view of the system. It shows what external actors "
        "want to achieve with the system, not the internal code structure.\n"
        "Required content:\n"
        "- Actors are external roles such as User, Admin, Teacher, Backend System, Payment Gateway.\n"
        "- Use cases are goals or capabilities written as verb phrases such as 'Sign In', 'Take Quiz', 'View Report'.\n"
        "- Put actors outside the system boundary and use cases inside the named system boundary.\n"
        "- Use actor-to-usecase links for participation.\n"
        "- Use <<include>> only between use cases when one use case always reuses another mandatory sub-flow.\n"
        "- Use <<extend>> only between use cases when one use case conditionally or optionally adds behavior to another.\n"
        "- Use generalization only between similar actors or between similar use cases when specialization is clearly justified.\n"
        "Do not show:\n"
        "- Screens, fragments, activities, repositories, APIs, components, or code classes as use cases.\n"
        "- Method names, file names, button ids, endpoints, or data models.\n"
        "- Include/extend relationships involving actors.\n"
        "Quality rules:\n"
        "- Use case names must be business/user goals, not nouns and not UI labels.\n"
        "- Prefer 4-10 meaningful use cases and 1-3 actors for a compact, useful view."
    ),
    "sequence_diagram": (
        "A sequence diagram is a time-ordered interaction scenario. It shows how runtime "
        "participants collaborate during one concrete flow from start to finish.\n"
        "Required content:\n"
        "- Participants are runtime collaborators such as User, Activity, ViewModel, Repository, API, Database.\n"
        "- Messages are concrete calls, events, callbacks, or returns in chronological order.\n"
        "- Focus on one scenario only.\n"
        "- Use alt/opt/loop groups only for meaningful branching or repetition within that scenario.\n"
        "Do not show:\n"
        "- Static package structure, use cases, deployment nodes, or unrelated screens.\n"
        "- A disconnected list of classes with no message flow.\n"
        "Quality rules:\n"
        "- sender and receiver must use exact participant names, never aliases.\n"
        "- Keep participants limited to the smallest set that explains the scenario."
    ),
    "activity_diagram": (
        "An activity diagram is a workflow view. It shows the actions, decisions, parallel "
        "paths, and stop conditions in one business or user process.\n"
        "Required content:\n"
        "- Steps should be actions or decisions, not classes or screens.\n"
        "- Use swimlanes only for real responsibility boundaries such as User, App, Backend.\n"
        "- Include at least one meaningful decision when the flow contains branching.\n"
        "Do not show:\n"
        "- Class relationships, component dependencies, or deployment topology.\n"
        "- Pure UI inventory without action flow.\n"
        "Quality rules:\n"
        "- Action labels should read like executable behavior such as 'Validate credentials' or 'Save profile'.\n"
        "- Decision labels should express a condition or question."
    ),
    "state_diagram": (
        "A state diagram is a lifecycle view of one entity or component. It shows the stable "
        "states that object can be in and the events or guards that move it between states.\n"
        "Required content:\n"
        "- Model one primary object or component only.\n"
        "- States should be stable conditions such as Idle, Loading, Authenticated, Error.\n"
        "- Include an initial transition from [*] into the first real state.\n"
        "- Label transitions with events, and use guards only when the condition matters.\n"
        "Do not show:\n"
        "- Multiple unrelated components in one diagram.\n"
        "- Message exchange order, package structure, or user goal lists.\n"
        "Quality rules:\n"
        "- State names should be stateful conditions, not screen names unless the diagram truly models screen lifecycle."
    ),
    "component_diagram": (
        "A component diagram is a high-level architecture view. It shows the major modules, "
        "subsystems, services, repositories, and interfaces and how they depend on each other.\n"
        "Required content:\n"
        "- Components should be coarse-grained architectural units, not every class.\n"
        "- Group components into feature areas or layers when that improves clarity.\n"
        "- Show dependency, usage, or provided/required interface relationships only when grounded in the code context.\n"
        "Do not show:\n"
        "- Time-ordered messages, user use cases, or deployment hardware.\n"
        "- Fine-grained field and method detail that belongs in a class diagram.\n"
        "Quality rules:\n"
        "- Use 4-10 components so the architecture remains readable."
    ),
    "package_diagram": (
        "A package diagram is a static organization view. It shows how the codebase is grouped "
        "into packages or layers and how those groups depend on each other.\n"
        "Required content:\n"
        "- Packages represent architectural layers, modules, or feature groups.\n"
        "- Each package should list a few representative classes.\n"
        "- Relationships should show dependencies between packages or between representative classes when that clarifies layering.\n"
        "Do not show:\n"
        "- Runtime call order, actors, user goals, or deployment nodes.\n"
        "- Raw screen navigation.\n"
        "Quality rules:\n"
        "- Prefer 3-6 packages that communicate a clear architecture."
    ),
    "deployment_diagram": (
        "A deployment diagram is a runtime environment view. It shows where software artifacts "
        "run and which nodes, services, databases, and external systems communicate at runtime.\n"
        "Required content:\n"
        "- Nodes are physical or logical runtime environments such as Android Device, API Server, Firebase, Database.\n"
        "- Children inside nodes are deployed artifacts or runtime components.\n"
        "- Relationships should be communication links labeled with protocol or integration type.\n"
        "Do not show:\n"
        "- Class fields/methods, user goals, or screen-to-screen navigation.\n"
        "- Package dependencies with no runtime meaning.\n"
        "Quality rules:\n"
        "- Keep the topology compact and grounded in actual external services mentioned by the code context."
    ),
    "navigation_diagram": (
        "A navigation diagram is a screen-flow view of the app. It shows screens and how users "
        "or the system move from one screen to another.\n"
        "Required content:\n"
        "- Nodes are screens only, typically Activities and Fragments.\n"
        "- Transitions are navigation actions such as button taps, menu actions, redirects, deep links, auth redirects, or back navigation.\n"
        "- Mark the entry screen and any screens that can end the flow.\n"
        "Do not show:\n"
        "- Business use cases, repositories, APIs, or architectural layers.\n"
        "- Internal code methods as nodes.\n"
        "Quality rules:\n"
        "- Use exact Activity or Fragment class names for screen identifiers.\n"
        "- Transition labels should describe the navigation trigger, not implementation details."
    ),
}


IR_TASK_INSTRUCTIONS = {
    "class_diagram": (
        "Analyze the code context and identify the 4-6 most important classes or interfaces. "
        "For each one include meaningful stereotype, package/layer, 2-3 key fields, and 2-4 "
        "important public methods. Add only relationships supported by the code context. "
        "If a relationship endpoint is external to the project, put it in external_classes."
    ),
    "usecase_diagram": (
        "Model the app from the perspective of external users or systems. Identify the main "
        "actors and the user goals they achieve with the app. Prefer business capabilities over "
        "screen names. Add include/extend only when the relationship is clearly mandatory or optional."
    ),
    "sequence_diagram": (
        "Trace one concrete end-to-end interaction from trigger to completion. Use only the "
        "runtime participants needed for that scenario. Number messages for readability and "
        "include one meaningful branch or optional path if the flow truly has one."
    ),
    "activity_diagram": (
        "Show one primary workflow from initiation to completion. Use 2-3 responsibility "
        "swimlanes when useful, keep the flow concrete, and include the key decisions that change the path."
    ),
    "state_diagram": (
        "Show the lifecycle of one important component or entity. Limit the diagram to the "
        "real states and transitions that matter, including entry/exit/do actions only when they add clarity."
    ),
    "component_diagram": (
        "Show the app's major architectural building blocks, grouped into feature packages or "
        "layers when helpful. Label each connection with the dependency or interaction type."
    ),
    "package_diagram": (
        "Show the main architectural packages or layers with representative classes in each. "
        "Use relationships to communicate package or inter-layer dependencies."
    ),
    "deployment_diagram": (
        "Show where the app runs and which runtime services or databases it depends on. Use node "
        "children to represent deployed artifacts or contained runtime components."
    ),
    "navigation_diagram": (
        "Map the screen-to-screen navigation flow using exact Activity or Fragment names from the "
        "code context. Define the transitions, entry screen, and exit points."
    ),
}
