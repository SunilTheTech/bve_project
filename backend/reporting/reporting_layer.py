"""Reporting Layer  —  WO-20260609-001, Sprint 3"""
from __future__ import annotations
import json, logging
from datetime import datetime
from pathlib import Path
import networkx as nx
from engine.simulation_engine  import SimulationRun
from engine.scenario_generator import ScenarioCoverageReport
from models.kg_models           import SimulationReport, ValidationResult, GraphValidationReport

logger = logging.getLogger(__name__)


class ReportingLayer:
    def generate(self, graph, run: SimulationRun, validation: ValidationResult,
                 scenario: ScenarioCoverageReport | None = None, output_dir="reports") -> SimulationReport:
        integrity: GraphValidationReport = graph.graph.get("validation_report") or GraphValidationReport(is_valid=True)
        timeline = [{"step": s.step, "event": s.event_id,
                     "virtual_start": round(s.virtual_time,4), "virtual_end": round(s.end_time,4),
                     "device_states": s.device_states, "triggered": s.triggered} for s in run.snapshots]
        coverage = {e: (e in run.completed_events) for e in sorted(graph.nodes())}
        if scenario:
            for n in scenario.covered_nodes: coverage[n] = True
        err_trace = [f"[{v.type.value}] {v.description}" for v in validation.violations if v.severity.value=="ERROR"]

        report = SimulationReport(
            status=validation.status, graph_validation=integrity,
            execution_timeline=timeline, simulation_logs=run.logs,
            violation_report=validation.violations, root_cause_trace=validation.rca,
            scenario_coverage=coverage, behaviour_validation=self._summary(validation, integrity, scenario),
            error_traceability=err_trace)

        self._write(report, output_dir, scenario)
        return report

    def _summary(self, val, gi, sc):
        parts = []
        if not gi.is_dag: parts.append(f"Graph has {len(gi.cycles)} cycle(s), {len(gi.deadlocked)} deadlocked.")
        errs = sum(1 for v in val.violations if v.severity.value=="ERROR")
        warns= sum(1 for v in val.violations if v.severity.value=="WARNING")
        parts.append("All events executed with no violations." if errs+warns==0
                     else f"Status: {val.status.value}. {errs} error(s), {warns} warning(s).")
        if sc: parts.append(f"DFS/BFS: {sc.total_paths} paths, {sc.fault_paths} fault(s), {sc.coverage_pct}% coverage.")
        return " ".join(parts)

    def _write(self, report, output_dir, sc):
        out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (out/f"simulation_report_{ts}.json").write_text(json.dumps(report.model_dump(), indent=2, default=str))
        (out/f"summary_{ts}.txt").write_text(self._txt(report))
        if sc:
            (out/f"scenario_coverage_{ts}.json").write_text(json.dumps({
                "total_paths": sc.total_paths, "fault_paths": sc.fault_paths,
                "coverage_pct": sc.coverage_pct, "covered_nodes": sorted(sc.covered_nodes),
                "paths": [{"path": p.path,"is_fault": p.is_fault,"reason": p.fault_reason} for p in sc.all_paths]
            }, indent=2))

    def _txt(self, r):
        lines = ["="*60, "BIW BEHAVIOURAL VALIDATION ENGINE — REPORT", "WO-20260609-001",
                 "="*60, f"Status    : {r.status.value}", f"DAG       : {r.graph_validation.is_dag}",
                 f"Valid     : {r.graph_validation.is_valid}", "", f"Summary   : {r.behaviour_validation}",
                 "", "── EXECUTION TIMELINE ──────────────────────────────────"]
        for e in r.execution_timeline:
            lines.append(f"  Step {e['step']:02d} | {e['event']:<24} T={e['virtual_start']:.3f}→{e['virtual_end']:.3f}s")
        if r.violation_report:
            lines += ["", "── VIOLATIONS ──────────────────────────────────────────"]
            for v in r.violation_report:
                lines.append(f"  [{v.severity.value}] [{v.type.value}] {v.description}")
        if r.root_cause_trace:
            lines += ["", "── ROOT CAUSE TRACE ────────────────────────────────────"]
            for rc in r.root_cause_trace: lines.append(f"  {rc}")
        lines += ["", "="*60]
        return "\n".join(lines)
