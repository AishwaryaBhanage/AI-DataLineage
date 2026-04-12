"""
dbt Manifest Loader
Reads target/manifest.json and returns typed Python objects.

The manifest is dbt's complete project snapshot: every model, source, test,
and macro along with the dependency graph (parent_map / child_map).

This module is PURE INGESTION — it reads and structures, it does not
analyse or debug.  Downstream modules (model_resolver, lineage_builder,
rule_engine) consume these dataclasses.

Usage:
    manifest = load_manifest("path/to/target/manifest.json")
    model = manifest.get_model("stg_orders")
    upstream = manifest.get_upstream("customer_revenue")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ManifestMetadata:
    """Top-level metadata about the dbt project and the run that created
    this manifest."""
    dbt_version: str
    project_name: str
    adapter_type: str
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "dbt_version": self.dbt_version,
            "project_name": self.project_name,
            "adapter_type": self.adapter_type,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class ColumnInfo:
    """A single documented column from schema.yml.
    Most models will have zero columns here — dbt only populates this
    if the user explicitly writes column docs/tests in schema.yml."""
    name: str
    description: str
    data_type: str      # often empty — depends on adapter + contract

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "data_type": self.data_type,
        }


@dataclass(frozen=True)
class ModelNode:
    """One dbt model extracted from the manifest.

    Key fields:
      raw_sql       — the Jinja+SQL template the developer wrote
      compiled_sql  — the fully rendered SQL after Jinja compilation
                      (None if dbt hasn't compiled yet)
      depends_on_models — unique_ids of upstream MODEL nodes
      depends_on_sources — unique_ids of upstream SOURCE nodes
      refs          — friendly ref names like ["stg_orders"]
    """
    unique_id: str              # "model.dbt_demo.stg_orders"
    name: str                   # "stg_orders"
    package_name: str           # "dbt_demo"
    schema: str                 # "main"
    file_path: str              # "models/stg_orders.sql"
    materialized: str           # "table" | "view" | "incremental" | "ephemeral"
    raw_sql: str                # original Jinja+SQL source
    compiled_sql: str | None    # rendered SQL (None if not compiled)
    depends_on_models: list[str]    # upstream model unique_ids
    depends_on_sources: list[str]   # upstream source unique_ids
    columns: dict[str, ColumnInfo]  # column_name -> ColumnInfo
    refs: list[str]                 # friendly ref names
    tags: list[str]
    description: str

    def to_dict(self) -> dict:
        return {
            "unique_id": self.unique_id,
            "name": self.name,
            "package_name": self.package_name,
            "schema": self.schema,
            "file_path": self.file_path,
            "materialized": self.materialized,
            "raw_sql": self.raw_sql,
            "compiled_sql": self.compiled_sql,
            "depends_on_models": self.depends_on_models,
            "depends_on_sources": self.depends_on_sources,
            "columns": {k: v.to_dict() for k, v in self.columns.items()},
            "refs": self.refs,
            "tags": self.tags,
            "description": self.description,
        }


@dataclass(frozen=True)
class SourceNode:
    """A dbt source — an external table declared in schema.yml.
    Sources are not SQL models; they represent raw tables in your warehouse
    that dbt reads FROM but does not manage."""
    unique_id: str              # "source.dbt_demo.raw.orders"
    name: str                   # "orders"
    source_name: str            # "raw" (the source group name)
    schema: str                 # "public"
    database: str               # "analytics"
    description: str
    columns: dict[str, ColumnInfo]

    def to_dict(self) -> dict:
        return {
            "unique_id": self.unique_id,
            "name": self.name,
            "source_name": self.source_name,
            "schema": self.schema,
            "database": self.database,
            "description": self.description,
            "columns": {k: v.to_dict() for k, v in self.columns.items()},
        }


@dataclass
class Manifest:
    """The complete parsed manifest.

    Provides dict-style access by model name (short name) and lookup
    helpers for upstream/downstream traversal.

    Internals:
      _models_by_name  — {short_name: ModelNode} for quick lookup
      _models_by_id    — {unique_id: ModelNode} for graph traversal
      parent_map       — copied directly from manifest (pre-computed by dbt)
      child_map        — copied directly from manifest (pre-computed by dbt)
    """
    metadata: ManifestMetadata
    models: dict[str, ModelNode]        # unique_id -> ModelNode
    sources: dict[str, SourceNode]      # unique_id -> SourceNode
    parent_map: dict[str, list[str]]    # unique_id -> [upstream unique_ids]
    child_map: dict[str, list[str]]     # unique_id -> [downstream unique_ids]

    # built in __post_init__
    _models_by_name: dict[str, ModelNode] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self):
        # Build name -> model index for convenient lookups.
        # If two packages have the same model name, last one wins (rare).
        self._models_by_name = {m.name: m for m in self.models.values()}

    # ── Lookup helpers ───────────────────────────────────────────────────

    def get_model(self, name: str) -> ModelNode | None:
        """Look up a model by short name (e.g. 'stg_orders').
        Returns None if the model doesn't exist."""
        return self._models_by_name.get(name)

    def get_model_by_id(self, unique_id: str) -> ModelNode | None:
        """Look up a model by its full unique_id."""
        return self.models.get(unique_id)

    def all_model_names(self) -> list[str]:
        """Return all model short names in the project."""
        return list(self._models_by_name.keys())

    def exists(self, name: str) -> bool:
        """Check if a model with this short name exists."""
        return name in self._models_by_name

    # ── Dependency traversal ─────────────────────────────────────────────

    def get_upstream(self, name: str) -> list[str]:
        """Direct upstream model names (one level up).

        Example:
            get_upstream("customer_revenue") -> ["stg_orders"]
        """
        model = self.get_model(name)
        if not model:
            return []
        parent_ids = self.parent_map.get(model.unique_id, [])
        return self._ids_to_names(parent_ids)

    def get_downstream(self, name: str) -> list[str]:
        """Direct downstream model names (one level down).

        Example:
            get_downstream("stg_orders") -> ["customer_revenue"]
        """
        model = self.get_model(name)
        if not model:
            return []
        child_ids = self.child_map.get(model.unique_id, [])
        return self._ids_to_names(child_ids)

    def get_all_upstream(self, name: str) -> list[str]:
        """All ancestors recursively. Closest first.

        Example:
            get_all_upstream("customer_revenue") -> ["stg_orders", "raw_orders"]
        """
        model = self.get_model(name)
        if not model:
            return []
        visited: set[str] = set()
        result: list[str] = []
        self._walk_up(model.unique_id, visited, result)
        return result

    def get_all_downstream(self, name: str) -> list[str]:
        """All descendants recursively. Closest first.

        Example:
            get_all_downstream("raw_orders") -> ["stg_orders", "customer_revenue"]
        """
        model = self.get_model(name)
        if not model:
            return []
        visited: set[str] = set()
        result: list[str] = []
        self._walk_down(model.unique_id, visited, result)
        return result

    # ── SQL access ───────────────────────────────────────────────────────

    def get_raw_sql(self, name: str) -> str:
        """Return the raw Jinja+SQL source of a model."""
        model = self.get_model(name)
        return model.raw_sql if model else ""

    def get_compiled_sql(self, name: str) -> str | None:
        """Return the compiled SQL (post-Jinja) of a model.
        Returns None if the model hasn't been compiled."""
        model = self.get_model(name)
        return model.compiled_sql if model else None

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "models": {k: v.to_dict() for k, v in self.models.items()},
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "parent_map": self.parent_map,
            "child_map": self.child_map,
        }

    # ── Private helpers ──────────────────────────────────────────────────

    def _ids_to_names(self, unique_ids: list[str]) -> list[str]:
        """Convert a list of unique_ids to short model names.
        Skips IDs that aren't models (e.g. sources, tests)."""
        names: list[str] = []
        for uid in unique_ids:
            model = self.models.get(uid)
            if model:
                names.append(model.name)
        return names

    def _walk_up(
        self, uid: str, visited: set[str], result: list[str]
    ) -> None:
        for parent_id in self.parent_map.get(uid, []):
            if parent_id in visited:
                continue
            visited.add(parent_id)
            model = self.models.get(parent_id)
            if model:
                result.append(model.name)
            self._walk_up(parent_id, visited, result)

    def _walk_down(
        self, uid: str, visited: set[str], result: list[str]
    ) -> None:
        for child_id in self.child_map.get(uid, []):
            if child_id in visited:
                continue
            visited.add(child_id)
            model = self.models.get(child_id)
            if model:
                result.append(model.name)
            self._walk_down(child_id, visited, result)


# ── Parsing functions (separated from Manifest class) ────────────────────

def _parse_refs(raw_refs: list) -> list[str]:
    """Handle both old and new dbt ref formats.

    Old (dbt < 1.5):  [["stg_orders"]]
    New (dbt >= 1.5): [{"name": "stg_orders", "package": null, "version": null}]
    """
    names: list[str] = []
    for ref in raw_refs:
        if isinstance(ref, dict):
            names.append(ref["name"])
        elif isinstance(ref, list):
            names.append(ref[0])
        elif isinstance(ref, str):
            names.append(ref)
    return names


def _parse_columns(raw_columns: dict) -> dict[str, ColumnInfo]:
    """Convert the raw columns dict from manifest into ColumnInfo objects."""
    result: dict[str, ColumnInfo] = {}
    for col_name, col_data in raw_columns.items():
        result[col_name] = ColumnInfo(
            name=col_name,
            description=col_data.get("description", ""),
            data_type=col_data.get("data_type", ""),
        )
    return result


def _parse_model_node(unique_id: str, raw: dict) -> ModelNode:
    """Parse a single model node from the manifest's nodes dict."""
    depends_on = raw.get("depends_on", {})
    dep_nodes = depends_on.get("nodes", [])

    return ModelNode(
        unique_id=unique_id,
        name=raw["name"],
        package_name=raw.get("package_name", ""),
        schema=raw.get("schema", ""),
        file_path=raw.get("original_file_path", ""),
        materialized=raw.get("config", {}).get("materialized", "table"),
        raw_sql=raw.get("raw_code", ""),
        compiled_sql=raw.get("compiled_code"),
        depends_on_models=[n for n in dep_nodes if n.startswith("model.")],
        depends_on_sources=[n for n in dep_nodes if n.startswith("source.")],
        columns=_parse_columns(raw.get("columns", {})),
        refs=_parse_refs(raw.get("refs", [])),
        tags=raw.get("tags", []),
        description=raw.get("description", ""),
    )


def _parse_source_node(unique_id: str, raw: dict) -> SourceNode:
    """Parse a single source node from the manifest's sources dict."""
    return SourceNode(
        unique_id=unique_id,
        name=raw["name"],
        source_name=raw.get("source_name", ""),
        schema=raw.get("schema", ""),
        database=raw.get("database", ""),
        description=raw.get("description", ""),
        columns=_parse_columns(raw.get("columns", {})),
    )


# ── Public API ───────────────────────────────────────────────────────────

def load_manifest(path: str | Path) -> Manifest:
    """Load and parse a dbt manifest.json file.

    Args:
        path: Path to target/manifest.json

    Returns:
        A fully parsed Manifest object with models, sources, and
        pre-computed dependency maps.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the file is not valid JSON or has no nodes.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"manifest.json not found at {path}\n"
            "Run `dbt compile` or `dbt run` inside your dbt project first."
        )

    with open(path) as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"manifest.json is not valid JSON: {e}")

    # ── Metadata ─────────────────────────────────────────────────────
    raw_meta = raw.get("metadata", {})
    metadata = ManifestMetadata(
        dbt_version=raw_meta.get("dbt_version", "unknown"),
        project_name=raw_meta.get("project_name", "unknown"),
        adapter_type=raw_meta.get("adapter_type", "unknown"),
        generated_at=raw_meta.get("generated_at", ""),
    )

    # ── Models ───────────────────────────────────────────────────────
    models: dict[str, ModelNode] = {}
    for uid, node_raw in raw.get("nodes", {}).items():
        if node_raw.get("resource_type") == "model":
            models[uid] = _parse_model_node(uid, node_raw)

    # ── Sources ──────────────────────────────────────────────────────
    sources: dict[str, SourceNode] = {}
    for uid, src_raw in raw.get("sources", {}).items():
        sources[uid] = _parse_source_node(uid, src_raw)

    # ── Dependency maps ──────────────────────────────────────────────
    # dbt pre-computes these — much more reliable than reconstructing
    # from depends_on, because they include sources and tests too.
    parent_map = raw.get("parent_map", {})
    child_map = raw.get("child_map", {})

    return Manifest(
        metadata=metadata,
        models=models,
        sources=sources,
        parent_map=parent_map,
        child_map=child_map,
    )
