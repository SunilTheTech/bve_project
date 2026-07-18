"""DFS/BFS Scenario Generator  —  WO-20260609-001, Sprint 3"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from collections import deque
import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPath:
    path: list[str]; is_fault: bool = False
    fault_node: str = ""; fault_reason: str = ""


@dataclass
class ScenarioCoverageReport:
    total_paths:     int; fault_paths: int; normal_paths: int
    all_paths:       list[ExecutionPath]
    covered_nodes:   set[str]; uncovered_nodes: set[str]; coverage_pct: float


class ScenarioGenerator:
    MAX_PATHS = 500

    def generate_dfs(self, graph: nx.DiGraph) -> ScenarioCoverageReport:
        roots = self._roots(graph); paths: list[ExecutionPath] = []
        for r in roots: self._dfs(graph, r, [r], paths)
        return self._report(graph, paths)

    def generate_bfs(self, graph: nx.DiGraph) -> ScenarioCoverageReport:
        roots = self._roots(graph); paths: list[ExecutionPath] = []
        q = deque([[r] for r in roots])
        while q and len(paths) < self.MAX_PATHS:
            cp = q.popleft(); node = cp[-1]
            succs = list(graph.successors(node))
            if not succs: paths.append(self._classify(graph, cp)); continue
            for nxt in succs:
                if nxt not in cp: q.append(cp + [nxt])
                else: paths.append(ExecutionPath(cp+[nxt], True, nxt, f"Cycle: '{nxt}' revisited"))
        return self._report(graph, paths)

    def _roots(self, graph):
        r = [n for n in graph.nodes() if graph.in_degree(n)==0]
        if r: return r
        rep = graph.graph.get("validation_report")
        if rep and rep.cycles: return [rep.cycles[0][0]]
        return list(graph.nodes())[:1]

    def _dfs(self, graph, node, path, paths):
        if len(paths) >= self.MAX_PATHS: return
        succs = list(graph.successors(node))
        if not succs: paths.append(self._classify(graph, path)); return
        for nxt in succs:
            if nxt in path: paths.append(ExecutionPath(path+[nxt], True, nxt, f"Cycle: '{nxt}' revisited"))
            else: self._dfs(graph, nxt, path+[nxt], paths)

    def _classify(self, graph, path):
        for i, node in enumerate(path):
            for pred in graph.predecessors(node):
                if graph[pred][node].get("type")=="precedes" and pred not in path[:i]:
                    return ExecutionPath(path, True, node, f"PRECEDES '{pred}' not satisfied before '{node}'")
        return ExecutionPath(path, False)

    def _report(self, graph, paths):
        all_nodes = set(graph.nodes())
        covered   = {n for p in paths for n in p.path}
        fc = sum(1 for p in paths if p.is_fault)
        pct = round(len(covered)/len(all_nodes)*100, 2) if all_nodes else 0.0
        logger.info("Scenario gen: %d paths | %d fault | %.1f%% coverage", len(paths), fc, pct)
        return ScenarioCoverageReport(len(paths), fc, len(paths)-fc, paths, covered, all_nodes-covered, pct)
