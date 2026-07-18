"""Validation Engine  —  WO-20260609-001, Sprint 3 (7 check categories)"""
from __future__ import annotations
import logging, re
import networkx as nx
from engine.simulation_engine import SimulationRun
from models.kg_models import (GraphValidationReport, ValidationResult,
                               ValidationStatus, Violation, ViolationType)

logger = logging.getLogger(__name__)


class ValidationEngine:
    def validate(self, graph: nx.DiGraph, run: SimulationRun) -> ValidationResult:
        v: list[Violation] = []
        rep: GraphValidationReport | None = graph.graph.get("validation_report")
        if rep and not rep.is_dag:
            v += [Violation(type=ViolationType.CYCLE, description=f"Cyclic dependency: {s}", severity=ValidationStatus.ERROR) for s in rep.cycle_summary]
            v += [Violation(type=ViolationType.DEADLOCK, event=e, description=f"'{e}' deadlocked.", severity=ValidationStatus.ERROR) for e in rep.deadlocked]
        v += self._sequence(graph, run)
        v += self._timing(graph, run)
        v += self._constraints(graph)
        v += self._safety(graph, run)
        v += self._race(run)
        status = self._agg(v)
        rca    = self._rca(v, graph)
        logger.info("Validation: %s — %d violation(s)", status.value, len(v))
        return ValidationResult(status=status, violations=v, rca=rca)

    def _sequence(self, graph, run):
        res = []; order = {s.event_id: s.step for s in run.snapshots}
        rep = graph.graph.get("validation_report")
        cyc = set(n for c in rep.cycles for n in c) if rep else set()
        ded = set(rep.deadlocked) if rep else set()
        for u, v, d in graph.edges(data=True):
            if d.get("type") not in ("precedes","enables"): continue
            us, vs = order.get(u), order.get(v)
            if us is None or vs is None:
                if u not in cyc and v not in cyc and u not in ded and v not in ded:
                    res.append(Violation(type=ViolationType.SEQUENCE, event=v, description=f"'{v}' never executed (req: '{u}').", severity=ValidationStatus.ERROR))
            elif us >= vs:
                res.append(Violation(type=ViolationType.SEQUENCE, event=v, description=f"'{u}' (step {us}) must precede '{v}' (step {vs}).", severity=ValidationStatus.ERROR))
        return res

    def _timing(self, graph, run):
        res = []; sm = {s.event_id: s.virtual_time for s in run.snapshots}
        for u, v, d in graph.edges(data=True):
            if d.get("type") not in ("precedes","enables"): continue
            ue = run.completed_end_times.get(u, 0.0); vs = sm.get(v)
            if vs is not None and vs < ue:
                res.append(Violation(type=ViolationType.TIMING, event=v,
                    description=f"'{v}' started T={vs:.3f}s before '{u}' ended T={ue:.3f}s (overlap={ue-vs:.4f}s).",
                    severity=ValidationStatus.ERROR))
        return res

    def _constraints(self, graph):
        res = []; specs = graph.graph.get("device_specs", {})
        for rule in graph.graph.get("rules", []):
            ok, det = self._eval(rule.get("condition",""), specs)
            if not ok:
                res.append(Violation(type=ViolationType.CONSTRAINT,
                    description=f"Rule '{rule['id']}': {rule['description']} — {det}", severity=ValidationStatus.ERROR))
        return res

    def _eval(self, cond, specs):
        m = re.search(r"(\w+)\s*(>=|<=|>|<|==)\s*(\w+)", cond)
        if not m: return True, "not evaluable"
        lk, op, rk = m.groups()
        lv = self._sv(lk, specs); rv = self._sv(rk, specs)
        if lv is None or rv is None: return True, f"missing spec values for '{lk}'/'{rk}'"
        ops = {">=": lv>=rv,"<=": lv<=rv,">": lv>rv,"<": lv<rv,"==": lv==rv}
        p = ops.get(op, True)
        return p, f"{lk}={lv} {op} {rk}={rv} → {'OK' if p else 'FAIL'}"

    def _sv(self, key, specs):
        for d in specs.values():
            if key in d: return float(d[key])
        return None

    def _safety(self, graph, run):
        res = []; order = {s.event_id: s.step for s in run.snapshots}; done = run.completed_events
        for rule in graph.graph.get("rules", []):
            cond = rule.get("condition","")
            if "requires" not in cond: continue
            parts = cond.split("requires"); dep, pre = parts[0].strip(), parts[1].strip()
            if dep not in done: continue
            if pre not in done:
                res.append(Violation(type=ViolationType.SAFETY, event=dep,
                    description=f"Interlock: '{dep}' executed without '{pre}' completing first.", severity=ValidationStatus.ERROR))
            elif order.get(dep, 0) <= order.get(pre, 0):
                res.append(Violation(type=ViolationType.SAFETY, event=dep,
                    description=f"Interlock: '{dep}' (step {order.get(dep)}) before '{pre}' (step {order.get(pre)}).", severity=ValidationStatus.ERROR))
        return res

    def _race(self, run):
        return [Violation(type=ViolationType.RACE, description=l, severity=ValidationStatus.WARNING)
                for l in run.logs if "[RACE]" in l]

    def _rca(self, violations, graph):
        rca = []
        for v in violations:
            if v.event and v.event in graph:
                preds = list(graph.predecessors(v.event))
                chain = " → ".join(preds + [v.event]) if preds else v.event
                rca.append(f"[{v.type.value}] Root cause chain: {chain}")
            else:
                rca.append(f"[{v.type.value}] {v.description}")
        return rca

    def _agg(self, violations):
        s = {v.severity for v in violations}
        if ValidationStatus.ERROR   in s: return ValidationStatus.ERROR
        if ValidationStatus.WARNING in s: return ValidationStatus.WARNING
        return ValidationStatus.PASS
