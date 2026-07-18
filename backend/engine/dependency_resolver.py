"""Dependency Resolver  —  WO-20260609-001, Sprint 2"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    topological_order: list[str]
    ready_set:         list[str]
    blocked_set:       set[str]
    cyclic_nodes:      set[str]
    deadlocked_nodes:  set[str]
    is_dag:            bool


class DependencyResolver:
    def resolve(self, graph: nx.DiGraph, completed: set[str] | None = None) -> ResolutionResult:
        completed = completed or set()
        report = graph.graph.get("validation_report")
        is_dag       = report.is_dag if report else nx.is_directed_acyclic_graph(graph)
        cyclic       = set(n for c in report.cycles for n in c) if (report and not is_dag) else set()
        deadlocked   = set(report.deadlocked) if (report and not is_dag) else set()

        if is_dag:
            topo = list(nx.topological_sort(graph))
        else:
            safe = [n for n in graph.nodes() if n not in cyclic]
            sub = graph.subgraph(safe)
            try:    topo = list(nx.topological_sort(sub)) + sorted(cyclic)
            except: topo = safe + sorted(cyclic)

        ready, blocked = [], set()
        for eid in topo:
            if eid in completed: continue
            if eid in cyclic or eid in deadlocked: blocked.add(eid); continue
            if self._pre_ok(graph, eid, completed, cyclic) and self._ena_ok(graph, eid, completed, cyclic):
                ready.append(eid)
            else:
                blocked.add(eid)
        logger.info("Resolution: %d ready | %d blocked | %d cyclic", len(ready), len(blocked), len(cyclic))
        return ResolutionResult(topo, ready, blocked, cyclic, deadlocked, is_dag)

    def _pre_ok(self, g, eid, done, cyc):
        return all(p in done for p in g.predecessors(eid) if g[p][eid].get("type")=="precedes" and p not in cyc)

    def _ena_ok(self, g, eid, done, cyc):
        return all(p in done for p in g.predecessors(eid) if g[p][eid].get("type")=="enables" and p not in cyc)
