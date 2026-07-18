"""Execution Graph Builder  —  WO-20260609-001, Sprint 1"""
from __future__ import annotations
import logging
import networkx as nx
from graph.graph_validator import GraphValidator
from models.kg_models import KnowledgeGraph, EventNode, RelationshipType

logger = logging.getLogger(__name__)

EDGE_WEIGHT = {
    RelationshipType.PRECEDES: 1.0, RelationshipType.ENABLES: 0.8,
    RelationshipType.TRIGGERS: 0.6, RelationshipType.HAS_CONSTRAINT: 0.5,
    RelationshipType.HAS_DURATION: 0.4,
}
TYPE_PRIORITY = ["precedes","enables","triggers","has_constraint","has_duration"]


class ExecutionGraphBuilder:
    def __init__(self): self._validator = GraphValidator()

    def build(self, kg: KnowledgeGraph) -> nx.DiGraph:
        graph = nx.DiGraph()
        timing_map = {t.event: t.duration for t in kg.timing}
        device_map = self._device_map(kg)
        resource_map = self._resource_map(kg)

        for event in kg.events:
            node = EventNode(id=event.id, duration=timing_map.get(event.id, 0.0),
                             device=device_map.get(event.id), resources=resource_map.get(event.id, []))
            graph.add_node(event.id, node=node, duration=node.duration,
                           device=node.device, resources=node.resources, state="PENDING")

        for rel in kg.relationships:
            if rel.from_event not in graph or rel.to_event not in graph:
                logger.warning("Skipping edge %s → %s: missing node", rel.from_event, rel.to_event); continue
            attrs = {"type": rel.type.value, "weight": EDGE_WEIGHT.get(rel.type, 1.0)}
            if rel.type == RelationshipType.HAS_CONSTRAINT and rel.constraint:
                attrs["constraint"] = rel.constraint
            if rel.type == RelationshipType.HAS_DURATION and rel.duration is not None:
                attrs["duration_override"] = rel.duration
                graph.nodes[rel.to_event]["duration"] = rel.duration
            if graph.has_edge(rel.from_event, rel.to_event):
                ex = graph[rel.from_event][rel.to_event]
                types = set(ex.get("types", [ex.get("type")])) | {rel.type.value}
                merged = next((t for t in TYPE_PRIORITY if t in types), rel.type.value)
                ex.update(attrs); ex["type"] = merged; ex["types"] = sorted(types)
            else:
                attrs["types"] = [rel.type.value]
                graph.add_edge(rel.from_event, rel.to_event, **attrs)

        for rule in kg.rules:
            graph.graph.setdefault("rules", []).append(
                {"id": rule.id, "description": rule.description, "condition": rule.condition})
        for spec in kg.device_specs:
            graph.graph.setdefault("device_specs", {})[spec.device] = spec.model_dump(exclude={"device"})
        resource_pool = {r.id: r.capacity for r in kg.resources}
        graph.graph["resource_pool"] = resource_pool

        report = self._validator.validate_graph(graph, kg)
        graph.graph["validation_report"] = report
        logger.info("Graph built: %d nodes, %d edges, is_dag=%s",
                    graph.number_of_nodes(), graph.number_of_edges(), report.is_dag)
        return graph

    def _device_map(self, kg):
        m = {}
        for e in kg.events:
            for d in kg.devices:
                if d.id.rstrip("0123456789").lower() in e.id.lower():
                    m[e.id] = d.id; break
        return m

    def _resource_map(self, kg):
        m = {}
        for r in kg.resources:
            stem = r.id.rstrip("0123456789").lower()
            for e in kg.events:
                if stem in e.id.lower():
                    m.setdefault(e.id, []).append(r.id)
        return m
