"""
Neo4j Graph Store — manages the code knowledge graph.

Schema
------
Nodes:
    (:Class {name, package, file_path, component_type, layer, language})
    (:Method {name, return_type, file_path})
    (:Field {name, type})
    (:Package {name})
    (:File {path, language})

Relationships:
    (:Class)-[:INHERITS_FROM]->(:Class)
    (:Class)-[:IMPLEMENTS]->(:Class)
    (:Class)-[:HAS_METHOD]->(:Method)
    (:Class)-[:HAS_FIELD]->(:Field)
    (:Class)-[:BELONGS_TO]->(:Package)
    (:Class)-[:DEFINED_IN]->(:File)
    (:Method)-[:CALLS]->(:Method)
    (:Method)-[:USES_TYPE]->(:Class)
    (:Class)-[:IMPORTS]->(:Class)

Falls back gracefully when Neo4j is unavailable.
"""

import logging
from typing import Optional, List, Dict, Any

log = logging.getLogger("graph_store")

_driver = None
_available = False


def init(uri: str, username: str, password: str, database: str = "neo4j") -> bool:
    """
    Initialize Neo4j connection. Returns True if successful.
    Safe to call multiple times — only connects once.
    """
    global _driver, _available
    if _driver is not None:
        return _available

    try:
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(uri, auth=(username, password))
        # Verify connectivity
        _driver.verify_connectivity()
        _available = True
        log.info("Connected to Neo4j at %s", uri)
        _create_schema(database)
        return True
    except Exception as e:
        log.warning("Neo4j not available (%s). GraphRAG disabled, "
                    "falling back to ChromaDB-only.", e)
        _driver = None
        _available = False
        return False


def is_available() -> bool:
    return _available


def close():
    global _driver, _available
    if _driver:
        _driver.close()
        _driver = None
        _available = False


def _get_session(database: str = None):
    """Get a Neo4j session."""
    import config
    db = database or getattr(config, "NEO4J_DATABASE", "neo4j")
    return _driver.session(database=db)


# ── Schema Setup ───────────────────────────────────────────────

def _create_schema(database: str = "neo4j"):
    """Create constraints and indexes for the knowledge graph."""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.qualified_name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Package) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX IF NOT EXISTS FOR (c:Class) ON (c.name)",
        "CREATE INDEX IF NOT EXISTS FOR (m:Method) ON (m.name)",
        "CREATE INDEX IF NOT EXISTS FOR (c:Class) ON (c.component_type)",
        "CREATE INDEX IF NOT EXISTS FOR (c:Class) ON (c.layer)",
    ]

    try:
        with _get_session(database) as session:
            for stmt in constraints + indexes:
                try:
                    session.run(stmt)
                except Exception:
                    pass  # constraint may already exist
        log.info("Neo4j schema created/verified.")
    except Exception as e:
        log.warning("Schema creation failed: %s", e)


# ── Graph Operations ──────────────────────────────────────────

def clear_graph():
    """Delete all nodes and relationships (for re-indexing)."""
    if not _available:
        return
    try:
        with _get_session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        log.info("Neo4j graph cleared.")
    except Exception as e:
        log.warning("Failed to clear graph: %s", e)


def upsert_file(file_path: str, language: str):
    """Create or update a File node."""
    if not _available:
        return
    with _get_session() as session:
        session.run(
            "MERGE (f:File {path: $path}) "
            "SET f.language = $language",
            path=file_path, language=language,
        )


def upsert_package(package_name: str):
    """Create or update a Package node."""
    if not _available or not package_name:
        return
    with _get_session() as session:
        session.run(
            "MERGE (p:Package {name: $name})",
            name=package_name,
        )


def upsert_class(name: str, package: str, file_path: str,
                 component_type: str = "Class", layer: str = "Other",
                 language: str = "java", annotations: List[str] = None):
    """Create or update a Class node with its relationships."""
    if not _available or not name:
        return

    qualified = f"{package}.{name}" if package else name
    annotations_str = ",".join(annotations) if annotations else ""

    with _get_session() as session:
        session.run(
            "MERGE (c:Class {qualified_name: $qn}) "
            "SET c.name = $name, c.package = $pkg, c.file_path = $fp, "
            "    c.component_type = $ct, c.layer = $layer, "
            "    c.language = $lang, c.annotations = $ann",
            qn=qualified, name=name, pkg=package, fp=file_path,
            ct=component_type, layer=layer, lang=language,
            ann=annotations_str,
        )

        # Link to package
        if package:
            session.run(
                "MATCH (c:Class {qualified_name: $qn}) "
                "MERGE (p:Package {name: $pkg}) "
                "MERGE (c)-[:BELONGS_TO]->(p)",
                qn=qualified, pkg=package,
            )

        # Link to file
        session.run(
            "MATCH (c:Class {qualified_name: $qn}) "
            "MERGE (f:File {path: $fp}) "
            "MERGE (c)-[:DEFINED_IN]->(f)",
            qn=qualified, fp=file_path,
        )


def add_inheritance(child_class: str, child_pkg: str,
                    parent_class: str):
    """Create INHERITS_FROM relationship."""
    if not _available or not child_class or not parent_class:
        return
    child_qn = f"{child_pkg}.{child_class}" if child_pkg else child_class

    with _get_session() as session:
        # Try to match parent by name (may not have package info)
        session.run(
            "MATCH (child:Class {qualified_name: $child_qn}) "
            "MERGE (parent:Class {name: $parent_name}) "
            "ON CREATE SET parent.qualified_name = $parent_name "
            "MERGE (child)-[:INHERITS_FROM]->(parent)",
            child_qn=child_qn, parent_name=parent_class,
        )


def add_interface(impl_class: str, impl_pkg: str, interface_name: str):
    """Create IMPLEMENTS relationship."""
    if not _available or not impl_class or not interface_name:
        return
    impl_qn = f"{impl_pkg}.{impl_class}" if impl_pkg else impl_class

    with _get_session() as session:
        session.run(
            "MATCH (impl:Class {qualified_name: $impl_qn}) "
            "MERGE (iface:Class {name: $iface_name}) "
            "ON CREATE SET iface.qualified_name = $iface_name, "
            "             iface.component_type = 'Interface' "
            "MERGE (impl)-[:IMPLEMENTS]->(iface)",
            impl_qn=impl_qn, iface_name=interface_name,
        )


def upsert_method(class_name: str, class_pkg: str,
                  method_name: str, return_type: str = "void"):
    """Create a Method node and link it to its class."""
    if not _available or not class_name or not method_name:
        return
    class_qn = f"{class_pkg}.{class_name}" if class_pkg else class_name
    method_id = f"{class_qn}.{method_name}"

    with _get_session() as session:
        session.run(
            "MERGE (m:Method {id: $mid}) "
            "SET m.name = $name, m.return_type = $ret, m.class_name = $cn "
            "WITH m "
            "MATCH (c:Class {qualified_name: $cqn}) "
            "MERGE (c)-[:HAS_METHOD]->(m)",
            mid=method_id, name=method_name, ret=return_type,
            cn=class_name, cqn=class_qn,
        )


def add_method_call(caller_class: str, caller_pkg: str,
                    caller_method: str, callee_method: str):
    """Create CALLS relationship between methods."""
    if not _available:
        return
    caller_qn = f"{caller_pkg}.{caller_class}" if caller_pkg else caller_class
    caller_mid = f"{caller_qn}.{caller_method}"

    with _get_session() as session:
        # Link to any method with that name (best-effort)
        session.run(
            "MATCH (caller:Method {id: $caller_id}) "
            "MATCH (callee:Method {name: $callee_name}) "
            "WHERE callee.id <> $caller_id "
            "MERGE (caller)-[:CALLS]->(callee)",
            caller_id=caller_mid, callee_name=callee_method,
        )


def upsert_field(class_name: str, class_pkg: str,
                 field_name: str, field_type: str):
    """Create a Field node and link to class + type class."""
    if not _available or not class_name or not field_name:
        return
    class_qn = f"{class_pkg}.{class_name}" if class_pkg else class_name
    field_id = f"{class_qn}.{field_name}"

    with _get_session() as session:
        session.run(
            "MERGE (f:Field {id: $fid}) "
            "SET f.name = $name, f.type = $ftype "
            "WITH f "
            "MATCH (c:Class {qualified_name: $cqn}) "
            "MERGE (c)-[:HAS_FIELD]->(f)",
            fid=field_id, name=field_name, ftype=field_type,
            cqn=class_qn,
        )

        # Link field to its type if it's a known class
        if field_type and field_type not in (
            "int", "long", "float", "double", "boolean", "byte",
            "char", "short", "String", "void", "Object",
            "Int", "Long", "Float", "Double", "Boolean",
        ):
            session.run(
                "MATCH (f:Field {id: $fid}) "
                "MATCH (t:Class {name: $tname}) "
                "MERGE (f)-[:OF_TYPE]->(t)",
                fid=field_id, tname=field_type.split("<")[0].split(".")[-1],
            )


def add_import(class_name: str, class_pkg: str, imported: str):
    """Create IMPORTS relationship."""
    if not _available or not imported:
        return
    class_qn = f"{class_pkg}.{class_name}" if class_pkg else class_name
    imported_simple = imported.split(".")[-1]

    with _get_session() as session:
        session.run(
            "MATCH (c:Class {qualified_name: $cqn}) "
            "MATCH (i:Class {name: $iname}) "
            "MERGE (c)-[:IMPORTS]->(i)",
            cqn=class_qn, iname=imported_simple,
        )


# ── Query Operations ──────────────────────────────────────────

def run_cypher(query: str, params: dict = None) -> List[Dict[str, Any]]:
    """Run a raw Cypher query and return results as list of dicts."""
    if not _available:
        return []
    try:
        with _get_session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    except Exception as e:
        log.warning("Cypher query failed: %s", e)
        return []


def get_class_dependencies(class_name: str) -> List[Dict]:
    """Get all classes that a given class depends on."""
    return run_cypher(
        "MATCH (c:Class {name: $name})-[r]->(dep) "
        "RETURN type(r) as relationship, "
        "       labels(dep) as dep_type, "
        "       dep.name as dep_name, "
        "       dep.qualified_name as dep_qualified",
        {"name": class_name},
    )


def get_class_dependents(class_name: str) -> List[Dict]:
    """Get all classes that depend on a given class."""
    return run_cypher(
        "MATCH (dep)-[r]->(c:Class {name: $name}) "
        "RETURN type(r) as relationship, "
        "       labels(dep) as dep_type, "
        "       dep.name as dep_name, "
        "       dep.qualified_name as dep_qualified",
        {"name": class_name},
    )


def get_call_chain(method_name: str, depth: int = 3) -> List[Dict]:
    """Trace the call chain from a method up to N levels deep."""
    return run_cypher(
        "MATCH path = (m:Method {name: $name})-[:CALLS*1.." + str(depth) + "]->(callee) "
        "RETURN [n IN nodes(path) | n.name] as call_chain, "
        "       length(path) as depth",
        {"name": method_name},
    )


def get_graph_schema_summary() -> str:
    """Return a human-readable summary of the graph for the LLM."""
    if not _available:
        return ""

    stats = run_cypher(
        "MATCH (n) "
        "RETURN labels(n)[0] as label, count(n) as count "
        "ORDER BY count DESC"
    )
    rel_stats = run_cypher(
        "MATCH ()-[r]->() "
        "RETURN type(r) as type, count(r) as count "
        "ORDER BY count DESC"
    )

    lines = ["Graph Schema Summary:"]
    lines.append("Nodes:")
    for s in stats:
        lines.append(f"  {s.get('label', '?')}: {s.get('count', 0)}")
    lines.append("Relationships:")
    for s in rel_stats:
        lines.append(f"  {s.get('type', '?')}: {s.get('count', 0)}")

    return "\n".join(lines)


def get_full_schema_for_cypher() -> str:
    """Return the schema description for LLM Cypher generation."""
    return """
Node Types:
- Class (properties: name, qualified_name, package, file_path, component_type, layer, language, annotations)
- Method (properties: id, name, return_type, class_name)
- Field (properties: id, name, type)
- Package (properties: name)
- File (properties: path, language)

Relationship Types:
- (Class)-[:INHERITS_FROM]->(Class)
- (Class)-[:IMPLEMENTS]->(Class)
- (Class)-[:HAS_METHOD]->(Method)
- (Class)-[:HAS_FIELD]->(Field)
- (Class)-[:BELONGS_TO]->(Package)
- (Class)-[:DEFINED_IN]->(File)
- (Method)-[:CALLS]->(Method)
- (Field)-[:OF_TYPE]->(Class)
- (Class)-[:IMPORTS]->(Class)

component_type values: Activity, Fragment, ViewModel, Service, BroadcastReceiver, ContentProvider, Adapter, DAO, Entity, Repository, DI Module, Interface, Class
layer values: UI, Business Logic, Data, Service, DI, Config, Other
"""
