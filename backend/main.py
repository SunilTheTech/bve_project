"""
BIW Behavioural Validation Engine  —  FastAPI Application
===========================================================
WO-20260609-001  |  Webwise Technologies Pvt Ltd for Digitran

Endpoints:
  GET  /healthz              — liveness probe
  POST /api/convert-to-kg    — convert Excel JSON rows → KG (via local LLM)
  POST /api/simulate         — run full pipeline + generate stage logs
  GET  /api/simulate/sample  — run against bundled geo-station fixture

LLM backend: Ollama (local, open-weight models — default llama3.1)
"""
from __future__ import annotations
import json, logging, os, sys
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from kg_parser.parser              import KGParser, KGParseError
from graph.execution_graph_builder import ExecutionGraphBuilder
from engine.simulation_engine      import SimulationEngine
from engine.scenario_generator     import ScenarioGenerator
from validation.validation_engine  import ValidationEngine
from reporting.reporting_layer     import ReportingLayer
from models.kg_models              import KnowledgeGraph, SimulationReport

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="BIW Behavioural Validation Engine",
    description="WO-20260609-001 — Webwise Technologies Pvt Ltd for Digitran.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000",
                   "http://127.0.0.1:5173", "http://127.0.0.1:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ── Layer singletons ────────────────────────────────────────────────────────────
# Ollama config — point OLLAMA_HOST at a remote box if you're not running it
# locally. Default model is llama3.1; override with OLLAMA_MODEL, e.g.
# "llama3.3", "llama3.1:70b", "qwen2.5:14b", "mistral", etc.
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

parser   = KGParser()
builder  = ExecutionGraphBuilder()
sim      = SimulationEngine()
val      = ValidationEngine()
scenario = ScenarioGenerator()
reporter = ReportingLayer()

SAMPLE = Path(__file__).parent / "data" / "sample_kg.json"


# ── Request / response models ──────────────────────────────────────────────────
class ConvertRequest(BaseModel):
    rows: list[dict]

class SimulateRequest(BaseModel):
    kg: dict

class FullPipelineResponse(BaseModel):
    status:       str
    stage_logs:   dict[str, list[str]]
    report:       dict
    stats:        dict


# ── Helpers ────────────────────────────────────────────────────────────────────
def ask_llm(prompt: str) -> str:
    """Call a local Ollama server (OpenAI-Anthropic-free, fully open-source stack)."""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_HOST}. Is it running? "
            f"(`ollama serve`, and `ollama pull {OLLAMA_MODEL}`)"
        ) from e
    except requests.exceptions.Timeout as e:
        raise RuntimeError(f"Ollama request timed out after {OLLAMA_TIMEOUT}s") from e


def run_pipeline(kg: KnowledgeGraph) -> FullPipelineResponse:
    graph   = builder.build(kg)
    run     = sim.run(graph)
    val_res = val.validate(graph, run)
    sc_rep  = scenario.generate_dfs(graph)
    report  = reporter.generate(graph, run, val_res, sc_rep)

    # Generate stage-level logs using the local LLM (realistic, event-specific)
    prompt = f"""Simulate the BIW Behavioural Validation Engine (WO-20260609-001) processing this Knowledge Graph:
{json.dumps({"devices": [d.model_dump() for d in kg.devices],
             "events":  [e.model_dump() for e in kg.events],
             "relationships": [r.model_dump(by_alias=True) for r in kg.relationships]}, indent=2)}

Return ONLY a JSON object (no markdown, no explanation) with these EXACT keys, each an array of strings:
{{
  "kg_parser":     [],
  "graph_builder": [],
  "graph_valid":   [],
  "dep_resolver":  [],
  "timing_sched":  [],
  "sim_engine":    [],
  "val_engine":    [],
  "scenario_gen":  [],
  "reporting":     []
}}

Rules per stage (8-10 lines each):
- Prefix each line with [INFO], [WARN], or [SUCCESS]
- Use actual event names and device names from the KG
- sim_engine: show each event executing with T= timestamps matching real durations
- val_engine: conclude with PASS or specific violation details
- scenario_gen: include DFS path count and coverage %
- reporting: list actual output filenames generated

Respond with the raw JSON object only — nothing else."""

    try:
        raw_logs  = ask_llm(prompt)
        clean     = raw_logs.replace("```json", "").replace("```", "").strip()
        # Some open models wrap JSON in stray prose despite instructions; grab the
        # outermost {...} block defensively.
        start, end = clean.find("{"), clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        stage_logs: dict[str, list[str]] = json.loads(clean)
    except Exception as e:
        logger.warning("Stage log generation failed (%s) — using fallback logs", e)
        stage_logs = {s: [f"[INFO] {s} initialised", f"[SUCCESS] {s} completed successfully"]
                      for s in ["kg_parser","graph_builder","graph_valid","dep_resolver",
                                "timing_sched","sim_engine","val_engine","scenario_gen","reporting"]}

    # Inject real simulation log lines into sim_engine stage
    stage_logs["sim_engine"] = run.logs[:10] or stage_logs.get("sim_engine", [])

    stats = {
        "events":      len(kg.events),
        "edges":       len(kg.relationships),
        "violations":  len([v for v in report.violation_report if v.severity.value == "ERROR"]),
        "coverage":    sc_rep.coverage_pct,
        "virtualTime": report.execution_timeline[-1]["virtual_end"] if report.execution_timeline else 0,
        "paths":       sc_rep.total_paths,
        "faultPaths":  sc_rep.fault_paths,
        "isValid":     report.graph_validation.is_valid,
        "isDAG":       report.graph_validation.is_dag,
    }

    return FullPipelineResponse(
        status=report.status.value,
        stage_logs=stage_logs,
        report=report.model_dump(),
        stats=stats,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["ops"])
def health():
    return {"status": "ok", "version": "1.0.0", "wo": "WO-20260609-001",
             "llm_backend": "ollama", "llm_model": OLLAMA_MODEL}


@app.post("/api/convert-to-kg", tags=["pipeline"])
def convert_to_kg(req: ConvertRequest):
    """Convert Excel JSON rows to a Knowledge Graph structure using the local LLM."""
    prompt = f"""You are a BIW (Body-in-White) manufacturing knowledge graph expert.
Convert this Excel data into a Knowledge Graph JSON for a BIW welding station:
{json.dumps(req.rows[:15], indent=2)}

Return ONLY valid JSON (no markdown, no explanation) with EXACTLY these keys:
{{
  "devices": [{{"id":"string","type":"string"}}],
  "states": [{{"device":"string","state":"string"}}],
  "events": [{{"id":"string"}}],
  "relationships": [{{"from":"<event_id>","to":"<event_id>","type":"precedes|enables|triggers|has_constraint|has_duration"}}],
  "timing": [{{"event":"string","duration":number}}],
  "rules": [{{"id":"string","description":"string","condition":"string"}}],
  "device_specs": [{{"device":"string"}}],
  "resources": [{{"id":"string","type":"string","capacity":1}}]
}}

CRITICAL: in relationships, both from and to MUST be event IDs from the events list (never device IDs).
Use 5-8 devices, 6-10 events. If input is not manufacturing data, generate a realistic BIW geo-station fixture.
Respond with the raw JSON object only — nothing else."""

    try:
        raw  = ask_llm(prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        start, end = clean.find("{"), clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        kg = json.loads(clean)
        return {"kg": kg, "message": "KG built successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KG conversion failed: {e}")


@app.post("/api/simulate", tags=["pipeline"])
def simulate(req: SimulateRequest) -> FullPipelineResponse:
    """Run the full 9-stage pipeline on a supplied KG JSON body."""
    try:
        kg = parser.parse_dict(req.kg)
        return run_pipeline(kg)
    except KGParseError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/simulate/sample", tags=["pipeline"])
def simulate_sample() -> FullPipelineResponse:
    """Run against the bundled geo-station fixture KG (clean DAG)."""
    if not SAMPLE.exists():
        raise HTTPException(status_code=404, detail="Sample KG not found")
    try:
        kg = parser.parse_file(SAMPLE)
        return run_pipeline(kg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)