"""Graph Validator — structural analysis of the CYOA branching graph.

Validates:
- Reachability: all nodes reachable from the starting node.
- Orphans: nodes that exist but have no incoming edges.
- Dead ends: non-ending nodes with no choices.
- Cycles: circular paths that could trap the reader.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphIssue:
    """A structural issue in the CYOA graph."""

    category: str  # "reachability", "orphan", "dead_end", "cycle"
    node_id: str
    message: str


@dataclass
class GraphResult:
    """Result of graph structure validation."""

    is_valid: bool
    issues: list[GraphIssue] = field(default_factory=list)
    reachable_nodes: list[str] = field(default_factory=list)
    unreachable_nodes: list[str] = field(default_factory=list)
    orphan_nodes: list[str] = field(default_factory=list)
    dead_end_nodes: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)

    def format_for_retry(self) -> str:
        """Format graph issues for LLM retry feedback."""
        if self.is_valid:
            return (
                f"Graph check: Valid. {len(self.reachable_nodes)} nodes reachable, "
                f"no orphans, no dead ends, no cycles."
            )
        lines = [f"Graph check: {len(self.issues)} issue(s):"]
        for issue in self.issues:
            lines.append(f"  [{issue.category}] {issue.node_id}: {issue.message}")
        return "\n".join(lines)


class GraphValidator:
    """Validates the structure of a CYOA branching graph.

    Usage:
        validator = GraphValidator()
        result = validator.check(graph_dict)
        if not result.is_valid:
            print(result.format_for_retry())
    """

    def check(self, graph: dict[str, Any]) -> GraphResult:
        """Run all graph structure checks.

        Args:
            graph: A dict conforming to graph.schema.json.

        Returns:
            GraphResult with detailed issue lists.
        """
        nodes = graph.get("nodes", [])
        node_ids = {n["node_id"] for n in nodes}
        start = graph.get("starting_node", "")

        issues: list[GraphIssue] = []

        # Build adjacency
        outgoing: dict[str, list[str]] = {}
        incoming: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for node in nodes:
            nid = node["node_id"]
            targets = [c["target_node"] for c in node.get("choices", []) if c.get("target_node")]
            outgoing[nid] = targets
            for t in targets:
                if t in incoming:
                    incoming[t].append(nid)

        # 1. Reachability (BFS from starting node)
        reachable = self._bfs_reachable(start, outgoing, node_ids)
        unreachable = node_ids - reachable
        for nid in sorted(unreachable):
            issues.append(
                GraphIssue(
                    category="reachability",
                    node_id=nid,
                    message=f"Node '{nid}' is unreachable from starting node '{start}'",
                )
            )

        # 2. Orphans (no incoming edges, excluding start)
        for nid, in_edges in incoming.items():
            if nid != start and len(in_edges) == 0:
                issues.append(
                    GraphIssue(
                        category="orphan",
                        node_id=nid,
                        message=f"Node '{nid}' has no incoming edges (orphan)",
                    )
                )

        # 3. Dead ends (no choices, not an ending)
        for node in nodes:
            nid = node["node_id"]
            has_choices = len(node.get("choices", [])) > 0
            is_ending = node.get("endings", {}).get("is_ending", False)
            if not has_choices and not is_ending and nid in reachable:
                issues.append(
                    GraphIssue(
                        category="dead_end",
                        node_id=nid,
                        message=f"Reachable node '{nid}' has no choices and is not marked as an ending",
                    )
                )

        # 4. Cycle detection (DFS with visited/recursion stack)
        cycles = self._detect_cycles(start, outgoing, reachable)
        for cycle in cycles:
            issues.append(
                GraphIssue(
                    category="cycle",
                    node_id=cycle[0],
                    message=f"Cycle detected: {' → '.join(cycle)} → {cycle[0]}",
                )
            )

        return GraphResult(
            is_valid=len(issues) == 0,
            issues=issues,
            reachable_nodes=sorted(reachable),
            unreachable_nodes=sorted(unreachable),
            orphan_nodes=sorted([i.node_id for i in issues if i.category == "orphan"]),
            dead_end_nodes=sorted([i.node_id for i in issues if i.category == "dead_end"]),
            cycles=cycles,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _bfs_reachable(
        start: str,
        outgoing: dict[str, list[str]],
        node_ids: set[str],
    ) -> set[str]:
        """BFS from start node to find all reachable nodes."""
        if start not in node_ids:
            return set()
        visited: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for target in outgoing.get(current, []):
                if target not in visited and target in node_ids:
                    queue.append(target)
        return visited

    @staticmethod
    def _detect_cycles(
        start: str,
        outgoing: dict[str, list[str]],
        reachable: set[str],
    ) -> list[list[str]]:
        """Detect cycles in the directed graph using DFS.

        Returns a list of cycles, each as a list of node IDs.
        """
        cycles: list[list[str]] = []
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {nid: WHITE for nid in reachable}
        parent: dict[str, str | None] = {nid: None for nid in reachable}

        def dfs(node: str) -> None:
            color[node] = GRAY
            for neighbor in outgoing.get(node, []):
                if neighbor not in color:  # skip nodes outside reachable set
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle — backtrack to collect it
                    cycle: list[str] = [neighbor, node]
                    curr = parent.get(node)
                    while curr is not None and curr != neighbor:
                        cycle.append(curr)
                        curr = parent.get(curr)
                    cycle.reverse()
                    if cycle not in cycles and cycle[::-1] not in cycles:
                        cycles.append(cycle)
                elif color[neighbor] == WHITE:
                    parent[neighbor] = node
                    dfs(neighbor)
            color[node] = BLACK

        dfs(start)
        return cycles
