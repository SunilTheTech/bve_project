"""Timing Scheduler  —  WO-20260609-001, Sprint 2"""
from __future__ import annotations
import heapq, logging
from dataclasses import dataclass, field
import networkx as nx

logger = logging.getLogger(__name__)
PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_NORMAL = 0, 1, 2


@dataclass(order=True)
class ScheduledEvent:
    earliest_start: float
    priority:       int
    event_id:       str   = field(compare=False)
    duration:       float = field(compare=False)
    end_time:       float = field(compare=False, default=0.0)
    resources_used: list  = field(compare=False, default_factory=list)


@dataclass
class SchedulingResult:
    ordered_queue:      list[ScheduledEvent]
    earliest_start_map: dict[str, float]
    race_conditions:    list[dict]
    timing_violations:  list[dict]
    resource_conflicts: list[dict]


class TimingScheduler:
    def schedule(self, graph, ready_set, current_time=0.0,
                 completed_end_times=None, resource_pool=None) -> SchedulingResult:
        cet = completed_end_times or {}
        pool = dict(resource_pool or {})
        heap, emap, races, tviol, rconf = [], {}, [], [], []

        for eid in ready_set:
            nd = graph.nodes[eid]
            es = self._es(graph, eid, current_time, cet)
            emap[eid] = es
            race = self._race(graph, eid, cet)
            if race: races.append(race); logger.warning("Race near '%s': %s", eid, race)
            viol = self._timing(graph, eid, es, cet)
            if viol: tviol.append(viol)
            needed = nd.get("resources", [])
            blocked_r = [r for r in needed if pool.get(r, 1) <= 0]
            if blocked_r: rconf.append({"event": eid, "blocked": blocked_r}); continue
            for r in needed:
                if r in pool: pool[r] -= 1
            heapq.heappush(heap, ScheduledEvent(es, self._prio(graph, eid), eid,
                           nd.get("duration", 0.0), es + nd.get("duration", 0.0), needed))

        queue = []
        while heap: queue.append(heapq.heappop(heap))
        logger.info("Scheduled %d events | %d races | %d resource conflicts", len(queue), len(races), len(rconf))
        return SchedulingResult(queue, emap, races, tviol, rconf)

    def _es(self, g, eid, ct, cet):
        return max([ct] + [cet.get(p, ct) for p in g.predecessors(eid)])

    def _race(self, g, eid, cet, threshold=0.05):
        ends = [cet[p] for p in g.predecessors(eid) if p in cet]
        if len(ends) < 2: return None
        span = max(ends) - min(ends)
        return {"event": eid, "window_s": round(span, 4)} if span < threshold else None

    def _timing(self, g, eid, es, cet):
        for p in g.predecessors(eid):
            if g[p][eid].get("type") == "precedes":
                pe = cet.get(p, 0.0)
                if pe > es: return {"event": eid, "pred": p, "overlap_s": round(pe - es, 4)}
        return None

    def _prio(self, g, eid):
        out = g.out_degree(eid)
        if out >= 2: return PRIORITY_CRITICAL
        if out == 1: return PRIORITY_HIGH
        return PRIORITY_NORMAL
