"""Simulation Engine  —  WO-20260609-001, Sprint 2"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
import networkx as nx
from engine.dependency_resolver import DependencyResolver
from engine.timing_scheduler    import TimingScheduler, ScheduledEvent
from models.kg_models           import SimulationState

logger = logging.getLogger(__name__)
MAX_STEPS = 2000


@dataclass
class SimulationSnapshot:
    step: int; event_id: str; virtual_time: float; end_time: float
    device_states: dict[str,str]; triggered: list[str]; log_entry: str


@dataclass
class SimulationRun:
    snapshots:           list[SimulationSnapshot] = field(default_factory=list)
    logs:                list[str]                = field(default_factory=list)
    completed_events:    set[str]                 = field(default_factory=set)
    completed_end_times: dict[str,float]          = field(default_factory=dict)
    skipped_events:      set[str]                 = field(default_factory=set)
    final_state:         SimulationState          = field(default_factory=SimulationState)


class SimulationEngine:
    def __init__(self):
        self.resolver  = DependencyResolver()
        self.scheduler = TimingScheduler()

    def run(self, graph: nx.DiGraph) -> SimulationRun:
        result = SimulationRun()
        state  = SimulationState(device_states=self._init_states(graph), pending=list(graph.nodes()))
        report = graph.graph.get("validation_report")
        blocked: set[str] = set()
        if report and not report.is_dag:
            blocked = set(report.deadlocked)
            for n in blocked:
                msg = f"[SKIP] '{n}' structurally blocked (cycle/deadlock)"
                result.logs.append(msg); result.skipped_events.add(n)
        pool = dict(graph.graph.get("resource_pool", {}))
        step = 0
        while step < MAX_STEPS:
            res = self.resolver.resolve(graph, result.completed_events)
            if not res.ready_set:
                rem = set(graph.nodes()) - result.completed_events - blocked
                if rem:
                    msg = f"[WARN] Halted — {len(rem)} event(s) unreachable: {sorted(rem)}"
                    result.logs.append(msg); logger.warning(msg)
                break
            sched = self.scheduler.schedule(graph, res.ready_set, state.virtual_time,
                                            result.completed_end_times, pool)
            for evt in sched.ordered_queue:
                step += 1
                snap = self._exec(graph, evt, state, step)
                result.snapshots.append(snap); result.logs.append(snap.log_entry)
                result.completed_events.add(evt.event_id)
                result.completed_end_times[evt.event_id] = evt.end_time
                state.virtual_time = max(state.virtual_time, evt.end_time)
        state.completed = sorted(result.completed_events)
        state.pending   = sorted(set(graph.nodes()) - result.completed_events - result.skipped_events)
        result.final_state = state
        logger.info("Simulation complete: %d executed | %.3fs virtual", len(result.completed_events), state.virtual_time)
        return result

    def _exec(self, graph, evt: ScheduledEvent, state, step):
        dev = graph.nodes[evt.event_id].get("device")
        ns  = self._infer(evt.event_id)
        if dev and ns: state.device_states[dev] = ns
        triggered = [s for s in graph.successors(evt.event_id) if graph[evt.event_id][s].get("type")=="triggers"]
        log = (f"[Step {step:02d}] T={evt.earliest_start:.3f}s  Event={evt.event_id}  "
               f"Dur={evt.duration:.2f}s  End={evt.end_time:.3f}s  "
               f"Device={dev or '—'}→{ns or '—'}  Triggers={triggered or []}")
        logger.info(log)
        return SimulationSnapshot(step, evt.event_id, evt.earliest_start, evt.end_time,
                                  dict(state.device_states), triggered, log)

    def _infer(self, eid):
        e = eid.lower()
        if "close"  in e: return "CLOSED"
        if "open"   in e: return "OPEN"
        if "start"  in e: return "MOVING"
        if "weld"   in e: return "WELDING"
        if "detect" in e: return "DETECTED"
        if "end"    in e: return "IDLE"
        return None

    def _init_states(self, graph):
        s = {}
        for _, d in graph.nodes(data=True):
            dev = d.get("device")
            if dev and dev not in s: s[dev] = "IDLE"
        return s
