"""Graph Validator  —  WO-20260609-001, Sprint 1"""
from __future__ import annotations
import logging
from collections import defaultdict
import networkx as nx
from models.kg_models import (GraphValidationReport, GraphValidationIssue,
                               GraphValidationIssueType, KnowledgeGraph, ValidationStatus)

logger = logging.getLogger(__name__)


class GraphValidator:
    def validate_graph(self, graph: nx.DiGraph, kg: KnowledgeGraph) -> GraphValidationReport:
        issues, duplicates, undefined, orphans, unreachable, cycles, deadlocked = [], [], [], [], [], [], []

        # 1. Duplicate nodes
        seen: dict[str,int] = defaultdict(int)
        for e in kg.events: seen[e.id] += 1
        for eid, n in seen.items():
            if n > 1:
                duplicates.append(eid)
                issues.append(GraphValidationIssue(type=GraphValidationIssueType.DUPLICATE_NODE, node=eid,
                    description=f"Event '{eid}' declared {n} times.", severity=ValidationStatus.ERROR))

        # 2. Undefined references
        declared = {e.id for e in kg.events}
        for rel in kg.relationships:
            for ref in (rel.from_event, rel.to_event):
                if ref not in declared and ref not in undefined:
                    undefined.append(ref)
                    issues.append(GraphValidationIssue(type=GraphValidationIssueType.UNDEFINED_NODE, node=ref,
                        description=f"Relationship references undeclared event '{ref}'.", severity=ValidationStatus.ERROR))

        # 3. Cycles + deadlocks
        is_dag = nx.is_directed_acyclic_graph(graph)
        cycle_summary: list[str] = []
        if not is_dag:
            cycles = list(nx.simple_cycles(graph))
            cyclic: set[str] = {n for c in cycles for n in c}
            for c in cycles:
                s = " → ".join(c + [c[0]]); cycle_summary.append(s)
                issues.append(GraphValidationIssue(type=GraphValidationIssueType.CYCLE,
                    description=f"Cyclic dependency: {s}", severity=ValidationStatus.ERROR))
            for node in graph.nodes():
                if node in cyclic:
                    deadlocked.append(node); continue
                preds = set(nx.ancestors(graph, node))
                if preds and preds.issubset(cyclic):
                    deadlocked.append(node)
            for node in sorted(set(deadlocked)):
                issues.append(GraphValidationIssue(type=GraphValidationIssueType.DEADLOCK, node=node,
                    description=f"Event '{node}' is deadlocked.", severity=ValidationStatus.ERROR))

        # 4. Orphan nodes
        for node in graph.nodes():
            if graph.degree(node) == 0:
                orphans.append(node)
                issues.append(GraphValidationIssue(type=GraphValidationIssueType.ORPHAN_NODE, node=node,
                    description=f"Event '{node}' has no edges.", severity=ValidationStatus.WARNING))

        # 5. Unreachable
        roots = [n for n in graph.nodes() if graph.in_degree(n) == 0]
        if roots:
            reachable = set(roots)
            for r in roots: reachable |= nx.descendants(graph, r)
            for node in sorted(set(graph.nodes()) - reachable):
                if node not in orphans:
                    unreachable.append(node)
                    issues.append(GraphValidationIssue(type=GraphValidationIssueType.UNREACHABLE, node=node,
                        description=f"Event '{node}' is unreachable.", severity=ValidationStatus.WARNING))

        is_valid = not any(i.severity == ValidationStatus.ERROR for i in issues)
        if is_valid: logger.info("Graph validation PASSED")
        else: logger.warning("Graph validation FAILED — %d issue(s)", len(issues))

        return GraphValidationReport(is_valid=is_valid, issues=issues, duplicate_nodes=duplicates,
            undefined_refs=undefined, orphan_nodes=orphans, unreachable=unreachable,
            cycles=cycles, deadlocked=sorted(set(deadlocked)), cycle_summary=cycle_summary, is_dag=is_dag)
