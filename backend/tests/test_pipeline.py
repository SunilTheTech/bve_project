"""
Test Suite — Behavioural Validation Engine
==========================================
WO-20260609-001  —  Run: pytest tests/ -v
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from kg_parser.parser              import KGParser, KGParseError
from graph.execution_graph_builder import ExecutionGraphBuilder
from graph.graph_validator         import GraphValidator
from engine.dependency_resolver    import DependencyResolver
from engine.simulation_engine      import SimulationEngine
from engine.scenario_generator     import ScenarioGenerator
from validation.validation_engine  import ValidationEngine
from reporting.reporting_layer     import ReportingLayer
from models.kg_models              import KnowledgeGraph

SAMPLE = Path(__file__).parent.parent / "data" / "sample_kg.json"


@pytest.fixture
def kg():
    return KGParser().parse_file(SAMPLE)

@pytest.fixture
def graph(kg):
    return ExecutionGraphBuilder().build(kg)


# ── KG Parser ──────────────────────────────────────────────────────────────────
def test_parser_loads_sample():
    kg = KGParser().parse_file(SAMPLE)
    assert len(kg.events) == 7
    assert len(kg.devices) == 5

def test_parser_rejects_bad_json():
    with pytest.raises(KGParseError):
        KGParser().parse_string("{bad json}")

def test_parser_rejects_missing_fields():
    with pytest.raises(KGParseError):
        KGParser().parse_dict({"devices": []})


# ── Graph Builder ──────────────────────────────────────────────────────────────
def test_builder_creates_all_nodes(graph):
    assert graph.number_of_nodes() == 7

def test_builder_creates_typed_edges(graph):
    types = {d["type"] for _, _, d in graph.edges(data=True)}
    assert "precedes" in types
    assert "enables"  in types

def test_builder_has_constraint_edge(graph):
    ce = [(u,v,d) for u,v,d in graph.edges(data=True) if d.get("type")=="has_constraint"]
    assert len(ce) == 1
    assert ce[0][2]["constraint"] == "ClampForce >= WeldForce"

def test_builder_merges_has_duration(graph):
    e = graph["WeldStart"]["WeldEnd"]
    assert "has_duration" in e["types"]
    assert e["duration_override"] == 0.8
    assert graph.nodes["WeldEnd"]["duration"] == 0.8


# ── Graph Validator ────────────────────────────────────────────────────────────
def test_validator_passes_clean_kg(graph, kg):
    r = GraphValidator().validate_graph(graph, kg)
    assert r.is_valid and r.is_dag

def test_validator_detects_undefined_node():
    raw = json.loads(SAMPLE.read_text())
    raw["relationships"].append({"from":"ClampClosed","to":"GhostEvent","type":"enables"})
    g2 = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    assert "GhostEvent" in g2.graph["validation_report"].undefined_refs

def test_validator_detects_duplicate_node():
    raw = json.loads(SAMPLE.read_text())
    raw["events"].append({"id": "ClampClose"})
    g2 = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    assert "ClampClose" in g2.graph["validation_report"].duplicate_nodes

def test_validator_detects_orphan_node():
    raw = json.loads(SAMPLE.read_text())
    raw["events"].append({"id": "OrphanEvent"})
    g2 = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    assert "OrphanEvent" in g2.graph["validation_report"].orphan_nodes

def test_validator_detects_cycle():
    raw = json.loads(SAMPLE.read_text())
    raw["relationships"].append({"from":"WeldEnd","to":"PanelLoaded","type":"precedes"})
    g2 = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    r2 = g2.graph["validation_report"]
    assert not r2.is_dag
    assert len(r2.cycles) >= 1


# ── Dependency Resolver ────────────────────────────────────────────────────────
def test_resolver_respects_precedence(graph):
    res = DependencyResolver().resolve(graph)
    o = res.topological_order
    assert o.index("ClampClose") < o.index("ClampClosed")
    assert o.index("WeldStart")  < o.index("WeldEnd")

def test_resolver_ready_set_starts_at_root(graph):
    res = DependencyResolver().resolve(graph, set())
    assert "PanelLoaded" in res.ready_set
    assert "WeldEnd" not in res.ready_set


# ── Simulation Engine ──────────────────────────────────────────────────────────
def test_simulation_executes_all_events(graph):
    run = SimulationEngine().run(graph)
    assert len(run.completed_events) == 7
    assert run.final_state.virtual_time > 0

def test_simulation_is_deterministic(graph):
    r1 = SimulationEngine().run(graph)
    r2 = SimulationEngine().run(graph)
    assert [(s.event_id, s.virtual_time) for s in r1.snapshots] == \
           [(s.event_id, s.virtual_time) for s in r2.snapshots]


# ── Validation Engine ──────────────────────────────────────────────────────────
def test_validation_pass_on_clean_kg(graph):
    run = SimulationEngine().run(graph)
    res = ValidationEngine().validate(graph, run)
    assert res.status.value == "PASS"
    assert res.violations == []

def test_validation_detects_constraint_violation():
    raw = json.loads(SAMPLE.read_text())
    for s in raw["device_specs"]:
        if s["device"] == "Clamp1": s["ClampForce"] = 1000
    g2  = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    run = SimulationEngine().run(g2)
    res = ValidationEngine().validate(g2, run)
    assert res.status.value == "ERROR"
    assert any(v.type.value == "CONSTRAINT" for v in res.violations)

def test_validation_detects_safety_violation():
    raw = json.loads(SAMPLE.read_text())
    raw["relationships"] = [r for r in raw["relationships"]
                            if not (r["from"]=="ClampClosed" and r["to"]=="RobotStart")]
    g2  = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    run = SimulationEngine().run(g2)
    res = ValidationEngine().validate(g2, run)
    assert any(v.type.value == "SAFETY" for v in res.violations)


# ── DFS/BFS Scenario Generator ─────────────────────────────────────────────────
def test_scenario_dfs_finds_paths(graph):
    r = ScenarioGenerator().generate_dfs(graph)
    assert r.total_paths >= 1 and r.coverage_pct > 0

def test_scenario_bfs_finds_paths(graph):
    assert ScenarioGenerator().generate_bfs(graph).total_paths >= 1

def test_scenario_detects_fault_on_cyclic_graph():
    raw = json.loads(SAMPLE.read_text())
    raw["relationships"].append({"from":"WeldEnd","to":"PanelLoaded","type":"precedes"})
    g2 = ExecutionGraphBuilder().build(KGParser().parse_dict(raw))
    assert ScenarioGenerator().generate_dfs(g2).fault_paths >= 1


# ── Reporting Layer ────────────────────────────────────────────────────────────
def test_reporting_generates_full_report(graph, tmp_path):
    run = SimulationEngine().run(graph)
    vr  = ValidationEngine().validate(graph, run)
    sc  = ScenarioGenerator().generate_dfs(graph)
    rp  = ReportingLayer().generate(graph, run, vr, sc, str(tmp_path))
    assert rp.status.value == "PASS"
    assert len(rp.execution_timeline) == 7

def test_reporting_writes_json_and_txt(graph, tmp_path):
    run = SimulationEngine().run(graph)
    vr  = ValidationEngine().validate(graph, run)
    ReportingLayer().generate(graph, run, vr, output_dir=str(tmp_path))
    assert list(tmp_path.glob("simulation_report_*.json"))
    assert list(tmp_path.glob("summary_*.txt"))


# ── End-to-end ──────────────────────────────────────────────────────────────────
def test_full_pipeline_pass():
    kg    = KGParser().parse_file(SAMPLE)
    graph = ExecutionGraphBuilder().build(kg)
    run   = SimulationEngine().run(graph)
    vr    = ValidationEngine().validate(graph, run)
    sc    = ScenarioGenerator().generate_dfs(graph)
    rp    = ReportingLayer().generate(graph, run, vr, sc)
    assert rp.status.value == "PASS"
    assert rp.graph_validation.is_dag
    assert rp.graph_validation.is_valid
    assert len(rp.execution_timeline) == 7
