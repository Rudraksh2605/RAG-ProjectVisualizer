"""
Regex-based parser for Java, Kotlin, XML (Android layout / manifest),
and Gradle build files.  Returns structured dicts describing each file's
contents — no external AST library required.
"""

import re
from typing import List, Dict, Optional
from utils.helpers import read_file_safe, detect_android_layer


# ────────────────────────────────────────────────────────────────
# Java / Kotlin parser
# ────────────────────────────────────────────────────────────────

_RE_PACKAGE = re.compile(r"^package\s+([\w.]+)", re.MULTILINE)
_RE_IMPORT = re.compile(r"^import\s+([\w.*]+)", re.MULTILINE)

_RE_CLASS = re.compile(
    r"(?:class|interface|object|enum)\s+"
    r"(?P<name>\w+)"
    r"(?:\s*<[^>]*>)?"
    r"(?:\s*(?:extends|:)\s*(?P<superclass>[\w.]+))?"
    r"(?:\s*(?:implements|,)\s*(?P<interfaces>[^{\n]+))?",
    re.MULTILINE,
)

_RE_METHOD = re.compile(
    r"(?:fun\s+)?"
    r"(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*"
    r"(?::\s*(?P<kt_return>[\w<>\[\]?,]+))?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_FIELD = re.compile(
    r"(?:val|var)\s+(?P<name>\w+)\s*:\s*(?P<type>[\w<>\[\]?,]+)"
    r"|(?P<type2>[\w<>\[\]?,]+)\s+(?P<name2>\w+)\s*[;=]",
    re.MULTILINE,
)


def parse_java_or_kotlin(path: str) -> Optional[Dict]:
    """Parse a .java or .kt file and return structured info."""
    content = read_file_safe(path)
    if not content:
        return None

    pkg_match = _RE_PACKAGE.search(content)
    package_name = pkg_match.group(1) if pkg_match else ""

    imports = _RE_IMPORT.findall(content)

    classes = []
    for m in _RE_CLASS.finditer(content):
        name = m.group("name")
        superclass = m.group("superclass") or ""
        interfaces_raw = m.group("interfaces") or ""
        interfaces = [i.strip() for i in interfaces_raw.split(",") if i.strip()]

        # Extract annotations from lines preceding the match
        pre_text = content[max(0, m.start() - 300):m.start()]
        annotations = re.findall(r"@(\w+)", pre_text)

        # Detect Android component type
        component_type = _detect_component_type(name, superclass, annotations)
        layer = detect_android_layer(component_type, name, superclass, annotations)

        classes.append({
            "name": name,
            "superclass": superclass,
            "interfaces": interfaces,
            "annotations": annotations,
            "component_type": component_type,
            "layer": layer,
        })

    methods = []
    for m in _RE_METHOD.finditer(content):
        mname = m.group("name")
        # Skip constructors and common noise
        if mname in ("if", "for", "while", "switch", "catch", "synchronized"):
            continue
        ret = m.group("kt_return") or "void"
        params = m.group("params").strip()
        methods.append({"name": mname, "return_type": ret.strip(), "params": params})

    fields = []
    for m in _RE_FIELD.finditer(content):
        fname = m.group("name") or m.group("name2") or ""
        ftype = m.group("type") or m.group("type2") or ""
        if fname and ftype:
            fields.append({"type": ftype, "name": fname})

    return {
        "path": path,
        "language": "kotlin" if path.endswith(".kt") else "java",
        "package": package_name,
        "imports": imports,
        "classes": classes,
        "methods": methods,
        "fields": fields,
        "source": content,
    }


def _detect_component_type(name: str, superclass: str,
                           annotations: List[str]) -> str:
    """Detect Android component type from class metadata."""
    s = superclass.lower()
    n = name.lower()
    ann_set = {a.lower() for a in annotations}

    if "activity" in s or n.endswith("activity"):
        return "Activity"
    if "fragment" in s or n.endswith("fragment"):
        return "Fragment"
    if "viewmodel" in s or n.endswith("viewmodel"):
        return "ViewModel"
    if "service" in s or n.endswith("service"):
        return "Service"
    if "broadcastreceiver" in s or n.endswith("receiver"):
        return "BroadcastReceiver"
    if "contentprovider" in s or n.endswith("provider"):
        return "ContentProvider"
    if "adapter" in n:
        return "Adapter"
    if "dao" in ann_set or n.endswith("dao"):
        return "DAO"
    if "entity" in ann_set or n.endswith("entity"):
        return "Entity"
    if "repository" in n:
        return "Repository"
    if "module" in ann_set or "hiltmodule" in ann_set:
        return "DI Module"
    if "interface" in s:      # fallback
        return "Interface"
    return "Class"


# ────────────────────────────────────────────────────────────────
# XML parser (Android layouts & manifest)
# ────────────────────────────────────────────────────────────────

_RE_XML_TAG = re.compile(r"<(\w[\w.]*)", re.MULTILINE)
_RE_ACTIVITY = re.compile(
    r'<activity[^>]*android:name\s*=\s*"([^"]+)"', re.MULTILINE
)
_RE_PERMISSION = re.compile(
    r'<uses-permission[^>]*android:name\s*=\s*"([^"]+)"', re.MULTILINE
)
_RE_SERVICE_XML = re.compile(
    r'<service[^>]*android:name\s*=\s*"([^"]+)"', re.MULTILINE
)
_RE_RECEIVER_XML = re.compile(
    r'<receiver[^>]*android:name\s*=\s*"([^"]+)"', re.MULTILINE
)
_RE_PROVIDER_XML = re.compile(
    r'<provider[^>]*android:name\s*=\s*"([^"]+)"', re.MULTILINE
)
_RE_PKG = re.compile(r'package\s*=\s*"([^"]+)"')
_RE_MIN_SDK = re.compile(r'android:minSdkVersion\s*=\s*"(\d+)"')
_RE_TARGET_SDK = re.compile(r'android:targetSdkVersion\s*=\s*"(\d+)"')


def parse_xml(path: str) -> Optional[Dict]:
    """Parse an Android XML file (layout or manifest)."""
    content = read_file_safe(path)
    if not content:
        return None

    is_manifest = "AndroidManifest" in path or "<manifest" in content

    if is_manifest:
        return _parse_manifest(path, content)
    else:
        return _parse_layout(path, content)


def _parse_manifest(path: str, content: str) -> Dict:
    pkg_m = _RE_PKG.search(content)
    return {
        "path": path,
        "type": "manifest",
        "package": pkg_m.group(1) if pkg_m else "",
        "activities": _RE_ACTIVITY.findall(content),
        "services": _RE_SERVICE_XML.findall(content),
        "receivers": _RE_RECEIVER_XML.findall(content),
        "providers": _RE_PROVIDER_XML.findall(content),
        "permissions": _RE_PERMISSION.findall(content),
        "min_sdk": (_RE_MIN_SDK.search(content) or type("", (), {"group": lambda s, i: ""})()).group(1),
        "target_sdk": (_RE_TARGET_SDK.search(content) or type("", (), {"group": lambda s, i: ""})()).group(1),
        "source": content,
    }


def _parse_layout(path: str, content: str) -> Dict:
    tags = _RE_XML_TAG.findall(content)
    # Filter out XML preamble tags
    widgets = [t for t in tags if t[0].isupper() or "." in t]
    return {
        "path": path,
        "type": "layout",
        "widgets": widgets,
        "source": content,
    }


# ────────────────────────────────────────────────────────────────
# Gradle parser
# ────────────────────────────────────────────────────────────────

_RE_DEPENDENCY = re.compile(
    r"""(?:implementation|api|compileOnly|testImplementation)\s*[\("]\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_RE_PLUGIN = re.compile(r"""id\s*[\("]\s*['"]([^'"]+)['"]""", re.MULTILINE)
_RE_MIN_SDK_GRADLE = re.compile(r"minSdk\s*=?\s*(\d+)")
_RE_TARGET_SDK_GRADLE = re.compile(r"targetSdk\s*=?\s*(\d+)")
_RE_COMPILE_SDK_GRADLE = re.compile(r"compileSdk\s*=?\s*(\d+)")


def parse_gradle(path: str) -> Optional[Dict]:
    content = read_file_safe(path)
    if not content:
        return None

    return {
        "path": path,
        "type": "gradle",
        "dependencies": _RE_DEPENDENCY.findall(content),
        "plugins": _RE_PLUGIN.findall(content),
        "min_sdk": (_RE_MIN_SDK_GRADLE.search(content) or type("", (), {"group": lambda s, i: ""})()).group(1),
        "target_sdk": (_RE_TARGET_SDK_GRADLE.search(content) or type("", (), {"group": lambda s, i: ""})()).group(1),
        "compile_sdk": (_RE_COMPILE_SDK_GRADLE.search(content) or type("", (), {"group": lambda s, i: ""})()).group(1),
        "source": content,
    }


# ────────────────────────────────────────────────────────────────
# Dispatcher
# ────────────────────────────────────────────────────────────────

def parse_file(path: str) -> Optional[Dict]:
    """Auto-detect file type and parse accordingly."""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("java", "kt"):
        return parse_java_or_kotlin(path)
    if ext == "xml":
        return parse_xml(path)
    if ext in ("gradle", "kts"):
        return parse_gradle(path)
    return None
