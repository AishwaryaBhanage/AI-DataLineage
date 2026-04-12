"""
dbt Lineage Builder
Constructs a networkx DAG from the manifest's pre-computed parent_map
and child_map, then provides traversal, path-finding, and
visualization-ready output.

Why use parent_map / child_map instead of depends_on?
  dbt pre-computes these maps during compilation.  They are canonical:
  they include model→model, model→source, and model→test edges.
  Reconstructing the graph from each node's depends_on is slower and
  misses edges that cross resource types.

Usage:
    from app.dbt.manifest_loader import load_manifest
    from app.dbt.run_results_loader import load_run_results
    from app.dbt.lineage_builder import LineageGraph

    manifest = load_manifest("target/manifest.json")
    results  = load_run_results("target/run_results.json")  # optional

    graph = LineageGraph(manifest, results)

    graph.get_upstream("customer_revenue")   # ["stg_orders"]
    graph.get_downstream("raw_orders")       # ["stg_orders"]
    graph.get_full_lineage("customer_revenue")  # all ancestors + descendants
    graph.to_dict("customer_revenue")        # visualization-ready JSON
    print(graph.ascii())                     # terminal-friendly tree
"""

from __future__ import annotations

import networkx as nx
from dataclasses import dataclass

from app.dbt.manifest_loader import Manifest, ModelNode
from app.dbt.run_results_loader import RunResults


# ── Node metadata ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NodeMeta:
    """Metadata attached to each graph node for visualization."""
    id: str                 # short model name
    materialized: str       # "table" | "view" | "incremental" | "ephemeral"
    schema: str             # "main", "staging", etc.
    file_path: str          # "models/stg_orders.sql"
    layer: str              # "source" | "intermediate" | "leaf" — computed
    status: str             # "success" | "error" | "skipped" | "unknown"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "materialized": self.materialized,
            "schema": self.schema,
            "file_path": self.file_path,
            "layer": self.layer,
            "status": self.status,
        }


# ── LineageGraph ─────────────────────────────────────────────────────────────

class LineageGraph:
    """Directed acyclic graph where edges point FROM upstream TO downstream.

    Example:
        raw_orders ──→ stg_orders ──→ customer_revenue

    Each node carries a NodeMeta with materialization, status, etc.
    """

    def __init__(
        self,
        manifest: Manifest,
        run_results: RunResults | None = None,
    ):
        self._manifest = manifest
        self._run_results = run_results
        self._graph: nx.DiGraph = self._build()

    # ── Build ────────────────────────────────────────────────────────────

    def _build(self) -> nx.DiGraph:
        """Build the DAG from manifest parent_map.

        For each model, we add a node with metadata, then add an edge
        from each parent to this model.  We only include model→model
        edges (skipping sources, tests, macros) because those are what
        the debugger visualizes.
        """
        G = nx.DiGraph()

        # Add all model nodes with metadata
        for model in self._manifest.models.values():
            G.add_node(model.name, meta=self._make_meta(model))

        # Add edges from parent_map (model→model only)
        for model in self._manifest.models.values():
            parent_ids = self._manifest.parent_map.get(model.unique_id, [])
            for pid in parent_ids:
                parent = self._manifest.get_model_by_id(pid)
                if parent:
                    G.add_edge(parent.name, model.name)

        # Compute layer for each node now that the graph is built
        for name in G.nodes:
            meta: NodeMeta = G.nodes[name]["meta"]
            layer = self._compute_layer(G, name)
            # NodeMeta is frozen, so rebuild with the correct layer
            G.nodes[name]["meta"] = NodeMeta(
                id=meta.id,
                materialized=meta.materialized,
                schema=meta.schema,
                file_path=meta.file_path,
                layer=layer,
                status=meta.status,
            )

        return G

    def _make_meta(self, model: ModelNode) -> NodeMeta:
        """Create initial NodeMeta for a model (layer filled in later)."""
        status = "unknown"
        if self._run_results:
            result = self._run_results.get_by_name(model.name)
            if result:
                status = result.status

        return NodeMeta(
            id=model.name,
            materialized=model.materialized,
            schema=model.schema,
            file_path=model.file_path,
            layer="",   # computed after graph is built
            status=status,
        )

    @staticmethod
    def _compute_layer(G: nx.DiGraph, name: str) -> str:
        """Determine a node's layer based on its position in the DAG.

        source:       no incoming edges (root of the pipeline)
        leaf:         no outgoing edges (final output)
        intermediate: everything else
        """
        in_deg = G.in_degree(name)
        out_deg = G.out_degree(name)
        if in_deg == 0:
            return "source"
        if out_deg == 0:
            return "leaf"
        return "intermediate"

    # ── Traversal (direct neighbors) ─────────────────────────────────────

    def get_upstream(self, model: str) -> list[str]:
        """Direct parents of a model (one level up).

        Example:
            get_upstream("customer_revenue") -> ["stg_orders"]
        """
        if model not in self._graph:
            return []
        return list(self._graph.predecessors(model))

    def get_downstream(self, model: str) -> list[str]:
        """Direct children of a model (one level down).

        Example:
            get_downstream("stg_orders") -> ["customer_revenue"]
        """
        if model not in self._graph:
            return []
        return list(self._graph.successors(model))

    # ── Traversal (recursive) ────────────────────────────────────────────

    def get_all_upstream(self, model: str) -> list[str]:
        """All ancestors in topological order (closest first).

        Example:
            get_all_upstream("customer_revenue")
            -> ["stg_orders", "raw_orders"]
        """
        if model not in self._graph:
            return []
        ancestors = nx.ancestors(self._graph, model)
        if not ancestors:
            return []
        subgraph = self._graph.subgraph(ancestors | {model})
        order = list(nx.topological_sort(subgraph))
        order = [n for n in order if n != model]
        return list(reversed(order))   # closest ancestor first

    def get_all_downstream(self, model: str) -> list[str]:
        """All descendants in topological order (closest first).

        Example:
            get_all_downstream("raw_orders")
            -> ["stg_orders", "customer_revenue"]
        """
        if model not in self._graph:
            return []
        descendants = nx.descendants(self._graph, model)
        if not descendants:
            return []
        subgraph = self._graph.subgraph(descendants | {model})
        order = list(nx.topological_sort(subgraph))
        return [n for n in order if n != model]

    def get_full_lineage(self, model: str) -> dict:
        """Complete lineage context for a model: ancestors, descendants,
        the model itself, and the blast radius.

        Returns:
            {
                "model": "customer_revenue",
                "upstream": ["stg_orders", "raw_orders"],
                "downstream": [],
                "impacted": [],          # same as downstream
                "paths_to_root": [...]
            }
        """
        return {
            "model": model,
            "upstream": self.get_all_upstream(model),
            "downstream": self.get_all_downstream(model),
            "impacted": self.get_all_downstream(model),
            "paths_to_root": self.paths_to_root(model),
        }

    # ── Path finding ─────────────────────────────────────────────────────

    def paths_to_root(self, model: str, max_paths: int = 20) -> list[list[str]]:
        """All paths from root source nodes down to this model.

        Useful for explaining the full ancestry chain:
            [["raw_orders", "stg_orders", "customer_revenue"]]

        Capped at max_paths to avoid exponential blowup on large DAGs.
        """
        if model not in self._graph:
            return []
        roots = self.root_models()
        paths: list[list[str]] = []
        for root in roots:
            if not nx.has_path(self._graph, root, model):
                continue
            for path in nx.all_simple_paths(self._graph, root, model):
                paths.append(path)
                if len(paths) >= max_paths:
                    return paths
        return paths

    # ── Inspection ───────────────────────────────────────────────────────

    def exists(self, model: str) -> bool:
        return model in self._graph

    def root_models(self) -> list[str]:
        """Models with no upstream dependencies (source layer)."""
        return [n for n in self._graph.nodes if self._graph.in_degree(n) == 0]

    def leaf_models(self) -> list[str]:
        """Models with no downstream dependents (final layer)."""
        return [n for n in self._graph.nodes if self._graph.out_degree(n) == 0]

    def all_models(self) -> list[str]:
        """All model names in topological order."""
        return list(nx.topological_sort(self._graph))

    def node_meta(self, model: str) -> NodeMeta | None:
        """Get the metadata for a specific node."""
        if model not in self._graph:
            return None
        return self._graph.nodes[model].get("meta")

    # ── Output formats ───────────────────────────────────────────────────

    def to_dict(self, model: str | None = None) -> dict:
        """Visualization-ready output.

        If model is given:  scope to that model's upstream + downstream
        If model is None:   return the full graph

        The output format is compatible with the existing Streamlit UI:
        - nodes: list (UI does G.add_nodes_from(nodes))
        - edges: [{"from": "a", "to": "b"}]
        - upstream, downstream, impacted, paths_to_root

        Each node is a rich dict with id, materialized, status, layer
        for frontends that want metadata.  For backward compatibility
        with the Streamlit UI (which expects plain strings), use
        to_dict_simple().
        """
        if model:
            relevant = (
                set(self.get_all_upstream(model))
                | {model}
                | set(self.get_all_downstream(model))
            )
            node_names = [n for n in relevant if n in self._graph]
            edges = [
                {"from": u, "to": v}
                for u, v in self._graph.edges
                if u in relevant and v in relevant
            ]
        else:
            node_names = list(self._graph.nodes)
            edges = [{"from": u, "to": v} for u, v in self._graph.edges]

        nodes = []
        for name in node_names:
            meta = self._graph.nodes[name].get("meta")
            if meta:
                nodes.append(meta.to_dict())
            else:
                nodes.append({"id": name})

        return {
            "nodes": nodes,
            "edges": edges,
            "upstream": self.get_all_upstream(model) if model else [],
            "downstream": self.get_all_downstream(model) if model else [],
            "impacted": self.get_all_downstream(model) if model else [],
            "paths_to_root": self.paths_to_root(model) if model else [],
        }

    def to_dict_simple(self, model: str | None = None) -> dict:
        """Backward-compatible output for the existing Streamlit UI.

        Same structure as to_dict() but nodes are plain strings
        instead of metadata dicts.  This is what the current
        render_lineage_graph() function expects.
        """
        full = self.to_dict(model)
        full["nodes"] = [
            n["id"] if isinstance(n, dict) else n
            for n in full["nodes"]
        ]
        return full

    # ── ASCII visualization ──────────────────────────────────────────────

    def ascii(self, model: str | None = None) -> str:
        """Render the lineage as an ASCII tree.

        If model is given, show only that model's subgraph.
        Otherwise, show the full graph rooted at source models.

        Example:
            raw_orders
              └── stg_orders
                    └── customer_revenue  [ERROR]
        """
        if model:
            relevant = (
                set(self.get_all_upstream(model))
                | {model}
                | set(self.get_all_downstream(model))
            )
            subgraph = self._graph.subgraph(relevant)
            roots = [n for n in subgraph.nodes if subgraph.in_degree(n) == 0]
        else:
            subgraph = self._graph
            roots = self.root_models()

        lines: list[str] = []
        visited: set[str] = set()

        def draw(node: str, prefix: str, is_last: bool, is_root: bool):
            if node in visited:
                return
            visited.add(node)

            # Build the line prefix
            if is_root:
                connector = ""
            else:
                connector = "└── " if is_last else "├── "

            # Status badge
            meta = self._graph.nodes[node].get("meta")
            badge = ""
            if meta and meta.status == "error":
                badge = "  [ERROR]"
            elif meta and meta.status == "skipped":
                badge = "  [SKIPPED]"

            lines.append(f"{prefix}{connector}{node}{badge}")

            # Recurse into children
            children = sorted(subgraph.successors(node))
            child_prefix = prefix + ("" if is_root else ("    " if is_last else "│   "))
            for i, child in enumerate(children):
                is_last_child = (i == len(children) - 1)
                draw(child, child_prefix, is_last_child, False)

        for root in sorted(roots):
            draw(root, "", is_last=True, is_root=True)

        return "\n".join(lines)
