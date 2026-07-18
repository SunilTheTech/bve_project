"""
Knowledge Graph Data Models  —  WO-20260609-001
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    PRECEDES       = "precedes"
    ENABLES        = "enables"
    TRIGGERS       = "triggers"
    HAS_CONSTRAINT = "has_constraint"
    HAS_DURATION   = "has_duration"


class ValidationStatus(str, Enum):
    PASS    = "PASS"
    WARNING = "WARNING"
    ERROR   = "ERROR"


class ViolationType(str, Enum):
    SEQUENCE   = "SEQUENCE"
    TIMING     = "TIMING"
    CONSTRAINT = "CONSTRAINT"
    SAFETY     = "SAFETY"
    RACE       = "RACE"
    CYCLE      = "CYCLE"
    DEADLOCK   = "DEADLOCK"


class GraphValidationIssueType(str, Enum):
    UNDEFINED_NODE = "UNDEFINED_NODE"
    DUPLICATE_NODE = "DUPLICATE_NODE"
    ORPHAN_NODE    = "ORPHAN_NODE"
    UNREACHABLE    = "UNREACHABLE"
    INVALID_EDGE   = "INVALID_EDGE"
    CYCLE          = "CYCLE"
    DEADLOCK       = "DEADLOCK"


class Device(BaseModel):
    id: str
    type: str


class StateEntry(BaseModel):
    device: str
    state: str


class EventEntry(BaseModel):
    id: str


class Relationship(BaseModel):
    from_event:  str              = Field(..., alias="from")
    to_event:    str              = Field(..., alias="to")
    type:        RelationshipType
    constraint:  Optional[str]   = None
    duration:    Optional[float] = None
    metadata:    Optional[dict]  = None
    model_config = {"populate_by_name": True}


class TimingEntry(BaseModel):
    event:    str
    duration: float


class Rule(BaseModel):
    id:          str
    description: str
    condition:   str


class Resource(BaseModel):
    id:       str
    type:     str
    capacity: int = 1


class DeviceSpec(BaseModel):
    device: str
    model_config = {"extra": "allow"}


class KnowledgeGraph(BaseModel):
    devices:       list[Device]
    states:        list[StateEntry]
    events:        list[EventEntry]
    relationships: list[Relationship]
    timing:        list[TimingEntry]
    rules:         list[Rule]
    device_specs:  list[DeviceSpec]
    resources:     list[Resource] = Field(default_factory=list)


class GraphValidationIssue(BaseModel):
    type:        GraphValidationIssueType
    node:        Optional[str]  = None
    description: str
    severity:    ValidationStatus


class GraphValidationReport(BaseModel):
    is_valid:        bool
    issues:          list[GraphValidationIssue] = Field(default_factory=list)
    duplicate_nodes: list[str]                  = Field(default_factory=list)
    undefined_refs:  list[str]                  = Field(default_factory=list)
    orphan_nodes:    list[str]                  = Field(default_factory=list)
    unreachable:     list[str]                  = Field(default_factory=list)
    cycles:          list[list[str]]            = Field(default_factory=list)
    deadlocked:      list[str]                  = Field(default_factory=list)
    cycle_summary:   list[str]                  = Field(default_factory=list)
    is_dag:          bool                       = True


class EventNode(BaseModel):
    id:          str
    duration:    float         = 0.0
    start_time:  Optional[float] = None
    end_time:    Optional[float] = None
    state:       str           = "PENDING"
    device:      Optional[str] = None
    resources:   list[str]     = Field(default_factory=list)
    constraints: list[str]     = Field(default_factory=list)


class SimulationState(BaseModel):
    virtual_time:  float         = 0.0
    device_states: dict[str,str] = Field(default_factory=dict)
    completed:     list[str]     = Field(default_factory=list)
    pending:       list[str]     = Field(default_factory=list)


class Violation(BaseModel):
    type:        ViolationType
    event:       Optional[str] = None
    description: str
    severity:    ValidationStatus


class ValidationResult(BaseModel):
    status:     ValidationStatus
    violations: list[Violation] = Field(default_factory=list)
    rca:        list[str]       = Field(default_factory=list)


class SimulationReport(BaseModel):
    status:               ValidationStatus
    graph_validation:     GraphValidationReport
    execution_timeline:   list[dict]
    simulation_logs:      list[str]
    violation_report:     list[Violation]
    root_cause_trace:     list[str]
    scenario_coverage:    dict[str, bool]
    behaviour_validation: str
    error_traceability:   list[str]
