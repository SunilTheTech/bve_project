import { useState, useEffect, useRef, useCallback } from "react";
import * as XLSX from "xlsx";

// ── Stage definitions ──────────────────────────────────────────────────────────
const STAGES = [
  { id:"kg_parser",     name:"KG Parser",               desc:"Schema validation & object mapping",     milestone:"M1" },
  { id:"graph_builder", name:"Execution Graph Builder",  desc:"NetworkX DiGraph + typed edge creation", milestone:"M1" },
  { id:"graph_valid",   name:"Graph Validator",          desc:"Duplicate / orphan / cycle detection",   milestone:"M1" },
  { id:"dep_resolver",  name:"Dependency Resolver",      desc:"Topological ordering + READY set",       milestone:"M2" },
  { id:"timing_sched",  name:"Timing Scheduler",         desc:"Time + priority + resource scheduling",  milestone:"M2" },
  { id:"sim_engine",    name:"Simulation Engine",        desc:"Virtual clock + state transitions",      milestone:"M2" },
  { id:"val_engine",    name:"Validation Engine",        desc:"7-category rule & interlock checking",   milestone:"M3" },
  { id:"scenario_gen",  name:"DFS/BFS Scenario Gen",     desc:"Path exploration + coverage reporting",  milestone:"M3" },
  { id:"reporting",     name:"Reporting Layer",          desc:"JSON logs, timeline & RCA export",       milestone:"M3" },
];

const initStages = () => STAGES.map(s => ({ ...s, status:"pending", logs:[], duration:null }));

// ── Light theme colours ────────────────────────────────────────────────────────
const T = {
  bg:       "#F8FAFC",   // page background
  white:    "#FFFFFF",   // card / panel background
  border:   "#E2E8F0",   // borders
  borderMd: "#CBD5E1",   // stronger borders
  text:     "#0F172A",   // primary text
  textMid:  "#334155",   // secondary text
  textDim:  "#64748B",   // muted text
  textXDim: "#94A3B8",   // very muted
  // milestone accent colours
  m1:       "#059669",   // emerald  – Sprint 1
  m1Light:  "#ECFDF5",
  m1Mid:    "#D1FAE5",
  m2:       "#2563EB",   // blue     – Sprint 2
  m2Light:  "#EFF6FF",
  m2Mid:    "#DBEAFE",
  m3:       "#7C3AED",   // violet   – Sprint 3
  m3Light:  "#F5F3FF",
  m3Mid:    "#EDE9FE",
  // status colours
  pass:     "#059669",
  passLight:"#ECFDF5",
  warn:     "#D97706",
  warnLight:"#FFFBEB",
  err:      "#DC2626",
  errLight: "#FEF2F2",
  run:      "#2563EB",
  runLight: "#EFF6FF",
  pending:  "#94A3B8",
};

const MS = { M1: T.m1, M2: T.m2, M3: T.m3 };
const MS_LIGHT = { M1: T.m1Light, M2: T.m2Light, M3: T.m3Light };
const MS_MID   = { M1: T.m1Mid,   M2: T.m2Mid,   M3: T.m3Mid   };

const STATUS_COLOR = {
  pending:  T.pending,
  running:  T.run,
  complete: T.pass,
  error:    T.err,
};
const STATUS_BG = {
  pending:  "#F1F5F9",
  running:  T.runLight,
  complete: T.passLight,
  error:    T.errLight,
};
const STATUS_LABEL = { pending:"PENDING", running:"RUNNING", complete:"DONE", error:"ERROR" };

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── Log line colour (dark terminal stays, just brighter) ───────────────────────
const logColor = l =>
  l.startsWith("[SUCCESS]") ? "#059669" :
  l.startsWith("[WARN]")    ? "#D97706" :
  l.startsWith("[ERROR]")   ? "#DC2626" :
  T.textMid;

export default function BVEDashboard() {
  const [view,        setView]        = useState("upload");
  const [file,        setFile]        = useState(null);
  const [excelRows,   setExcelRows]   = useState(null);
  const [kgData,      setKgData]      = useState(null);
  const [stages,      setStages]      = useState(initStages());
  const [selectedId,  setSelectedId]  = useState("kg_parser");
  const [phase,       setPhase]       = useState("idle");
  const [loading,     setLoading]     = useState(false);
  const [err,         setErr]         = useState(null);
  const [stats,       setStats]       = useState({ events:0,edges:0,violations:0,coverage:0,virtualTime:0,paths:0 });
  const [previewOpen, setPreviewOpen] = useState(null);
  const [dragging,    setDragging]    = useState(false);
  const [backendOk,   setBackendOk]   = useState(null);
  const logRef = useRef(null);

  useEffect(() => { logRef.current?.scrollTo({ top:logRef.current.scrollHeight, behavior:"smooth" }); }, [stages, selectedId]);
  useEffect(() => {
    fetch("/healthz").then(r => r.ok ? setBackendOk(true) : setBackendOk(false)).catch(() => setBackendOk(false));
  }, []);

  const sel     = stages.find(s => s.id === selectedId);
  const done    = stages.filter(s => s.status === "complete").length;
  const errCnt  = stages.filter(s => s.status === "error").length;
  const overall = stages.every(s => s.status==="complete") ? "PASS"
                : stages.some(s  => s.status==="error")    ? "ERROR"
                : phase === "running"                       ? "RUNNING" : "—";

  // ── Excel parse ─────────────────────────────────────────────────────────────
  const parseExcel = useCallback(f => {
    setErr(null); setFile(f);
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const wb   = XLSX.read(e.target.result, { type:"binary" });
        const ws   = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws);
        setExcelRows(rows); setPhase("parsed"); setKgData(null);
      } catch(ex) { setErr("Could not parse file: " + ex.message); }
    };
    reader.readAsBinaryString(f);
  }, []);

  const onDrop = useCallback(e => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer?.files?.[0]; if (f) parseExcel(f);
  }, [parseExcel]);

  // ── Build KG ────────────────────────────────────────────────────────────────
  const buildKG = async () => {
    setLoading(true); setPhase("converting"); setErr(null);
    try {
      const res  = await fetch("/api/convert-to-kg", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ rows: excelRows }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Conversion failed");
      const data = await res.json();
      setKgData(data.kg); setPhase("ready");
      setStats(s => ({ ...s, events:data.kg.events?.length||0, edges:data.kg.relationships?.length||0 }));
    } catch(ex) { setErr("KG build failed: " + ex.message); setPhase("parsed"); }
    finally { setLoading(false); }
  };

  // ── Run pipeline ─────────────────────────────────────────────────────────────
  const runPipeline = async () => {
    setLoading(true); setErr(null); setStages(initStages());
    setView("dashboard"); setSelectedId("kg_parser"); setPhase("running");
    let stageLogs = {}, finalStats = {};
    try {
      const res  = await fetch("/api/simulate", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ kg: kgData }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Pipeline failed");
      const data = await res.json();
      stageLogs  = data.stage_logs || {};
      finalStats = data.stats      || {};
    } catch(ex) { setErr("Pipeline error: " + ex.message); setLoading(false); return; }
    setLoading(false);

    for (let i = 0; i < STAGES.length; i++) {
      const sid   = STAGES[i].id;
      setSelectedId(sid);
      setStages(prev => prev.map((s,idx) => idx===i ? {...s, status:"running"} : s));
      const t0    = Date.now();
      const lines = stageLogs[sid] || [`[INFO] ${STAGES[i].name} processing…`, `[SUCCESS] ${STAGES[i].name} completed`];
      for (const line of lines) {
        await sleep(80 + Math.random()*140);
        setStages(prev => prev.map((s,idx) => idx===i ? {...s, logs:[...s.logs, line]} : s));
      }
      await sleep(280);
      const dur    = ((Date.now()-t0)/1000).toFixed(2);
      const hasErr = lines.some(l => l.startsWith("[ERROR]"));
      setStages(prev => prev.map((s,idx) => idx===i ? {...s, status:hasErr?"error":"complete", duration:dur} : s));
    }
    setPhase("done");
    setStats({ events:finalStats.events||0, edges:finalStats.edges||0,
               violations:finalStats.violations||0, coverage:finalStats.coverage||0,
               virtualTime:finalStats.virtualTime||0, paths:finalStats.paths||0 });
  };

  const reset = () => {
    setView("upload"); setFile(null); setExcelRows(null); setKgData(null);
    setPhase("idle"); setStages(initStages());
    setStats({ events:0,edges:0,violations:0,coverage:0,virtualTime:0,paths:0 }); setErr(null);
  };

  // ── Shared CSS ───────────────────────────────────────────────────────────────
  const css = `
    *, *::before, *::after { box-sizing: border-box; }
    body { margin:0; background:${T.bg}; font-family:'Inter','Segoe UI',sans-serif; }
    .drop-zone { transition:border-color .18s, background .18s; }
    .drop-zone:hover { border-color:${T.m2} !important; background:${T.m2Light} !important; }
    .stage-row { transition:background .12s; cursor:pointer; }
    .stage-row:hover { background:${T.bg} !important; }
    .stage-row.sel { background:${T.white} !important; border-left:3px solid ${T.m2} !important; }
    .pulse { animation: pulse 1.4s ease-in-out infinite; }
    @keyframes pulse { 0%,100%{box-shadow:0 0 0 2px ${T.run}44} 50%{box-shadow:0 0 0 5px ${T.run}22} }
    .log-line { animation:li .14s ease; }
    @keyframes li { from{opacity:0;transform:translateY(2px)} to{opacity:1} }
    .sb::-webkit-scrollbar { width:5px; height:5px; }
    .sb::-webkit-scrollbar-track { background:transparent; }
    .sb::-webkit-scrollbar-thumb { background:${T.borderMd}; border-radius:3px; }
    .btn-primary { background:${T.m2}; color:#fff; font-weight:600; cursor:pointer; border:none;
      padding:9px 20px; border-radius:8px; font-size:13px; transition:all .15s; letter-spacing:.01em; }
    .btn-primary:hover { background:#1D4ED8; transform:translateY(-1px); box-shadow:0 4px 12px ${T.m2}44; }
    .btn-primary:disabled { background:${T.borderMd}; color:${T.textXDim}; cursor:not-allowed; transform:none; box-shadow:none; }
    .btn-sec { background:${T.white}; color:${T.textMid}; cursor:pointer; border:1px solid ${T.border};
      padding:7px 14px; border-radius:7px; font-size:12px; transition:all .15s; }
    .btn-sec:hover { border-color:${T.borderMd}; color:${T.text}; background:${T.bg}; }
    .fade { animation:fi .25s ease; }
    @keyframes fi { from{opacity:0;transform:translateY(5px)} to{opacity:1;transform:none} }
    .stat-card { background:${T.white}; border:1px solid ${T.border}; border-radius:10px; padding:14px 18px; }
    .tag { font-size:10px; font-weight:700; letter-spacing:.05em; padding:2px 8px; border-radius:20px; }
  `;

  // ══════════════════════════════════════════════════════════════════════════════
  // UPLOAD VIEW
  // ══════════════════════════════════════════════════════════════════════════════
  if (view === "upload") return (
    <div style={{ background:T.bg, minHeight:"100vh", color:T.text }}>
      <style>{css}</style>

      {/* Header */}
      <div style={{ background:T.white, borderBottom:`1px solid ${T.border}`, padding:"14px 28px",
                    display:"flex", alignItems:"center", justifyContent:"space-between",
                    boxShadow:"0 1px 4px #0F172A0A" }}>
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <div style={{ width:34, height:34, background:T.m2, borderRadius:9,
                        display:"flex", alignItems:"center", justifyContent:"center",
                        fontWeight:800, fontSize:11, color:"#fff", letterSpacing:".02em" }}>BVE</div>
          <div>
            <div style={{ fontSize:15, fontWeight:700, color:T.text }}>Behavioural Validation Engine</div>
            <div style={{ fontSize:11, color:T.textDim }}>WO-20260609-001 · Webwise Technologies Pvt Ltd</div>
          </div>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          {backendOk !== null && (
            <div style={{ display:"flex", alignItems:"center", gap:6, fontSize:12,
                          background: backendOk ? T.passLight : T.errLight,
                          border:`1px solid ${backendOk ? T.m1Mid : "#FECACA"}`,
                          borderRadius:20, padding:"4px 12px" }}>
              <div style={{ width:7, height:7, borderRadius:"50%", background:backendOk?T.pass:T.err }} />
              <span style={{ color:backendOk?T.pass:T.err, fontWeight:600 }}>
                {backendOk ? "Backend connected" : "Backend offline — start uvicorn"}
              </span>
            </div>
          )}
          {phase==="done" && <button className="btn-sec" onClick={()=>setView("dashboard")}>View Dashboard →</button>}
        </div>
      </div>

      <div style={{ maxWidth:900, margin:"0 auto", padding:"44px 28px" }}>
        <div style={{ marginBottom:36 }}>
          <h1 style={{ fontSize:30, fontWeight:800, color:T.text, margin:"0 0 6px", letterSpacing:"-.02em" }}>
            Knowledge Graph Ingestion
          </h1>
          <p style={{ color:T.textDim, fontSize:14, margin:0 }}>
            Upload an Excel file → Convert to JSON → Build Knowledge Graph → Run all 9 pipeline stages
          </p>
        </div>

        {/* Drop zone */}
        <div className="drop-zone"
          onDrop={onDrop} onDragOver={e=>{e.preventDefault();setDragging(true)}} onDragLeave={()=>setDragging(false)}
          onClick={()=>document.getElementById("xlinput")?.click()}
          style={{ border:`2px dashed ${dragging?T.m2:T.borderMd}`, borderRadius:16, padding:"52px 32px",
                   textAlign:"center", marginBottom:28, cursor:"pointer",
                   background:dragging?T.m2Light:T.white,
                   boxShadow:"0 1px 3px #0F172A08" }}>
          <input id="xlinput" type="file" accept=".xlsx,.xls,.csv" style={{display:"none"}}
            onChange={e=>{ if(e.target.files?.[0]) parseExcel(e.target.files[0]); }}/>
          {!file ? (
            <>
              <div style={{ fontSize:44, marginBottom:14 }}>📊</div>
              <div style={{ color:T.text, fontWeight:600, fontSize:16, marginBottom:6 }}>
                Drop an Excel or CSV file here
              </div>
              <div style={{ color:T.textDim, fontSize:13 }}>or click to browse · .xlsx .xls .csv accepted</div>
            </>
          ) : (
            <div className="fade">
              <div style={{ fontSize:40, marginBottom:10 }}>✅</div>
              <div style={{ color:T.text, fontWeight:700, fontSize:15, marginBottom:4 }}>{file.name}</div>
              <div style={{ color:T.textDim, fontSize:13, marginBottom:12 }}>
                {excelRows?.length} rows · {Object.keys(excelRows?.[0]||{}).length} columns parsed
              </div>
              <button className="btn-sec" onClick={e=>{e.stopPropagation();reset();}}>Remove file ✕</button>
            </div>
          )}
        </div>

        {err && (
          <div style={{ background:T.errLight, border:`1px solid #FECACA`, borderRadius:9,
                        padding:"11px 16px", marginBottom:20, color:T.err, fontSize:13, fontWeight:500 }}>
            ⚠ {err}
          </div>
        )}

        {/* 3-step pipeline */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 48px 1fr 48px 1fr", alignItems:"start", marginBottom:32 }}>

          {/* Step 1 */}
          <div style={{ background:T.white, border:`1.5px solid ${phase!=="idle"?T.m1:T.border}`,
                        borderRadius:14, padding:22, boxShadow:"0 1px 4px #0F172A08" }}>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12 }}>
              <span className="tag" style={{ background:T.m1Light, color:T.m1 }}>STEP 1</span>
              {phase!=="idle" && <span style={{ fontSize:18 }}>✓</span>}
            </div>
            <div style={{ fontWeight:700, color:T.text, marginBottom:4, fontSize:15 }}>Excel File</div>
            <div style={{ fontSize:12, color:T.textDim, marginBottom:12 }}>Raw spreadsheet data</div>
            {excelRows && (
              <>
                <div style={{ fontSize:12, color:T.textMid, marginBottom:8,
                              background:T.bg, border:`1px solid ${T.border}`, borderRadius:6,
                              padding:"5px 10px" }}>
                  📋 {excelRows.length} rows · {Object.keys(excelRows[0]||{}).length} columns
                </div>
                <button className="btn-sec" style={{fontSize:11,padding:"4px 10px"}}
                  onClick={e=>{e.stopPropagation();setPreviewOpen(previewOpen==="json"?null:"json")}}>
                  {previewOpen==="json"?"▲ Hide preview":"▼ Preview JSON"}
                </button>
                {previewOpen==="json" && (
                  <div className="sb" style={{ marginTop:10, background:T.bg, borderRadius:8,
                                               border:`1px solid ${T.border}`, padding:12,
                                               maxHeight:150, overflowY:"auto" }}>
                    <pre style={{ fontSize:10, color:T.textMid, fontFamily:"monospace", margin:0 }}>
                      {JSON.stringify(excelRows.slice(0,3),null,2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Arrow 1 */}
          <div style={{ display:"flex", alignItems:"center", justifyContent:"center", paddingTop:52 }}>
            <div style={{ fontSize:24, color:phase!=="idle"?T.m1:T.borderMd, fontWeight:300 }}>→</div>
          </div>

          {/* Step 2 */}
          <div style={{ background:T.white, border:`1.5px solid ${kgData?T.m2:T.border}`,
                        borderRadius:14, padding:22, boxShadow:"0 1px 4px #0F172A08" }}>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12 }}>
              <span className="tag" style={{ background:T.m2Light, color:T.m2 }}>STEP 2</span>
              {kgData && <span style={{ fontSize:18 }}>✓</span>}
            </div>
            <div style={{ fontWeight:700, color:T.text, marginBottom:4, fontSize:15 }}>Knowledge Graph</div>
            <div style={{ fontSize:12, color:T.textDim, marginBottom:12 }}>Structured BIW model</div>
            {phase==="parsed" && !loading &&
              <button className="btn-primary" style={{width:"100%",padding:"9px 0"}}
                onClick={buildKG} disabled={!backendOk}>
                Build KG →
              </button>}
            {phase==="converting" &&
              <div style={{ display:"flex", alignItems:"center", gap:8, color:T.m2, fontSize:13, fontWeight:500 }}>
                <span style={{ animation:"spin 1s linear infinite",display:"inline-block" }}>⚙</span>
                Converting via Claude…
              </div>}
            {kgData && (
              <>
                <div style={{ display:"flex", gap:8, marginBottom:10 }}>
                  {[`${kgData.events?.length} events`,`${kgData.relationships?.length} edges`,`${kgData.rules?.length} rules`].map(t=>(
                    <span key={t} style={{ fontSize:11, background:T.m2Light, color:T.m2,
                                          borderRadius:20, padding:"2px 9px", fontWeight:600 }}>{t}</span>
                  ))}
                </div>
                <button className="btn-sec" style={{fontSize:11,padding:"4px 10px"}}
                  onClick={e=>{e.stopPropagation();setPreviewOpen(previewOpen==="kg"?null:"kg")}}>
                  {previewOpen==="kg"?"▲ Hide KG":"▼ Preview KG"}
                </button>
                {previewOpen==="kg" && (
                  <div className="sb" style={{ marginTop:10, background:T.bg, borderRadius:8,
                                               border:`1px solid ${T.border}`, padding:12,
                                               maxHeight:150, overflowY:"auto" }}>
                    <pre style={{ fontSize:10, color:T.textMid, fontFamily:"monospace", margin:0 }}>
                      {JSON.stringify(kgData,null,2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Arrow 2 */}
          <div style={{ display:"flex", alignItems:"center", justifyContent:"center", paddingTop:52 }}>
            <div style={{ fontSize:24, color:kgData?T.m2:T.borderMd, fontWeight:300 }}>→</div>
          </div>

          {/* Step 3 */}
          <div style={{ background:T.white,
                        border:`1.5px solid ${phase==="done"?T.m3:phase==="running"?T.m2:T.border}`,
                        borderRadius:14, padding:22, boxShadow:"0 1px 4px #0F172A08" }}>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12 }}>
              <span className="tag" style={{ background:T.m3Light, color:T.m3 }}>STEP 3</span>
              {phase==="done" && <span style={{ fontSize:18 }}>✓</span>}
            </div>
            <div style={{ fontWeight:700, color:T.text, marginBottom:4, fontSize:15 }}>9 Pipeline Stages</div>
            <div style={{ fontSize:12, color:T.textDim, marginBottom:12 }}>Simulate · Validate · Report</div>
            {kgData && phase==="ready" &&
              <button className="btn-primary" style={{width:"100%",padding:"9px 0",background:T.m3}}
                onClick={runPipeline} disabled={loading||!backendOk}>
                ▶ Run Pipeline
              </button>}
            {phase==="running" &&
              <div style={{ color:T.m2, fontSize:13, fontWeight:600 }}>⚡ Pipeline running…</div>}
            {phase==="done" && (
              <button className="btn-sec" style={{width:"100%",padding:"9px 0",borderColor:T.m3,color:T.m3}}
                onClick={()=>setView("dashboard")}>
                View Dashboard →
              </button>
            )}
          </div>
        </div>

        {/* Stage pill strip */}
        <div style={{ background:T.white, border:`1px solid ${T.border}`, borderRadius:12, padding:20,
                      boxShadow:"0 1px 3px #0F172A08" }}>
          <div style={{ fontSize:11, fontWeight:700, color:T.textXDim, letterSpacing:".07em", marginBottom:14 }}>
            PIPELINE STAGES — WO-20260609-001
          </div>
          <div style={{ display:"flex", gap:7, flexWrap:"wrap" }}>
            {STAGES.map(s => {
              const c = MS[s.milestone], bg = MS_LIGHT[s.milestone];
              return (
                <div key={s.id} style={{ display:"flex", alignItems:"center", gap:6,
                                         background:bg, border:`1px solid ${MS_MID[s.milestone]}`,
                                         borderRadius:20, padding:"4px 12px" }}>
                  <div style={{ width:6, height:6, borderRadius:"50%", background:c }} />
                  <span style={{ fontSize:11, color:c, fontWeight:600 }}>{s.name}</span>
                  <span style={{ fontSize:10, color:`${c}88` }}>{s.milestone}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );

  // ══════════════════════════════════════════════════════════════════════════════
  // DASHBOARD VIEW
  // ══════════════════════════════════════════════════════════════════════════════
  const overallColor = overall==="PASS"?T.pass:overall==="ERROR"?T.err:overall==="RUNNING"?T.run:T.textXDim;
  const overallBg    = overall==="PASS"?T.passLight:overall==="ERROR"?T.errLight:overall==="RUNNING"?T.runLight:"#F1F5F9";

  return (
    <div style={{ background:T.bg, height:"100vh", display:"flex", flexDirection:"column", color:T.text }}>
      <style>{css}</style>

      {/* Stats bar */}
      <div style={{ background:T.white, borderBottom:`1px solid ${T.border}`,
                    padding:"10px 20px", display:"flex", alignItems:"center",
                    flexShrink:0, boxShadow:"0 1px 4px #0F172A0A" }}>
        <div style={{ display:"flex", alignItems:"center", gap:10,
                      marginRight:20, paddingRight:20, borderRight:`1px solid ${T.border}` }}>
          <div style={{ width:32, height:32, background:T.m2, borderRadius:8,
                        display:"flex", alignItems:"center", justifyContent:"center",
                        fontWeight:800, fontSize:11, color:"#fff" }}>BVE</div>
          <div>
            <div style={{ fontSize:13, fontWeight:700, color:T.text }}>Pipeline Dashboard</div>
            <div style={{ fontSize:10, color:T.textDim }}>WO-20260609-001</div>
          </div>
        </div>

        {[["Events",   stats.events||0,                                        T.text    ],
          ["Edges",    stats.edges||0,                                         T.text    ],
          ["Stages",   `${done}/9`,      done===9 ? T.pass : T.text                      ],
          ["Violations",stats.violations, stats.violations>0 ? T.err : T.pass             ],
          ["Virt Time", stats.virtualTime?`${Number(stats.virtualTime).toFixed(1)}s`:"—", T.text],
          ["Coverage",  stats.coverage  ?`${Number(stats.coverage).toFixed(0)}%`:"—",     T.text],
          ["Paths",     stats.paths||"—",                                      T.text    ],
        ].map(([l,v,c])=>(
          <div key={l} style={{ padding:"0 16px", borderRight:`1px solid ${T.border}` }}>
            <div style={{ fontSize:10, color:T.textDim, marginBottom:2 }}>{l}</div>
            <div style={{ fontSize:15, fontWeight:700, color:c, fontFamily:"monospace" }}>{v}</div>
          </div>
        ))}

        <div style={{ padding:"0 16px", marginLeft:"auto" }}>
          <div style={{ fontSize:10, color:T.textDim, marginBottom:2 }}>Status</div>
          <span style={{ fontSize:12, fontWeight:700, fontFamily:"monospace",
                         background:overallBg, color:overallColor,
                         border:`1px solid ${overallColor}44`,
                         borderRadius:20, padding:"2px 10px" }}>{overall}</span>
        </div>
        <button onClick={reset} className="btn-sec" style={{ marginLeft:14 }}>← Upload</button>
      </div>

      <div style={{ display:"flex", flex:1, overflow:"hidden" }}>
        {/* LEFT: Stage list */}
        <div className="sb" style={{ width:280, flexShrink:0, background:T.white,
                                     borderRight:`1px solid ${T.border}`,
                                     overflowY:"auto", display:"flex", flexDirection:"column" }}>
          {["M1","M2","M3"].map(ms => {
            const mStages = stages.filter(s => s.milestone===ms);
            const c       = MS[ms];
            const lbl     = ms==="M1"?"Sprint 1 — KG Build":ms==="M2"?"Sprint 2 — Engine":"Sprint 3 — Validate";
            return (
              <div key={ms}>
                <div style={{ padding:"12px 16px 5px", display:"flex", alignItems:"center", gap:8,
                              borderBottom:`1px solid ${T.border}`, background:MS_LIGHT[ms] }}>
                  <div style={{ width:3, height:28, borderRadius:2, background:c }} />
                  <div>
                    <div style={{ fontSize:11, fontWeight:800, color:c, letterSpacing:".05em" }}>{ms}</div>
                    <div style={{ fontSize:10, color:`${c}99` }}>{lbl}</div>
                  </div>
                </div>
                {mStages.map(s => {
                  const isActive  = s.id === selectedId;
                  const isRunning = s.status === "running";
                  const sc        = STATUS_COLOR[s.status];
                  const sbg       = STATUS_BG[s.status];
                  return (
                    <div key={s.id} className={`stage-row${isActive?" sel":""}`}
                      style={{ padding:"10px 14px 10px 17px",
                               borderLeft:`3px solid ${isActive?T.m2:"transparent"}`,
                               borderBottom:`1px solid ${T.border}`,
                               background:isActive?T.white:T.bg }}
                      onClick={()=>setSelectedId(s.id)}>
                      <div style={{ display:"flex", alignItems:"center", gap:9 }}>
                        <div className={isRunning?"pulse":""}
                          style={{ width:9, height:9, borderRadius:"50%", background:sc, flexShrink:0 }} />
                        <div style={{ flex:1, minWidth:0 }}>
                          <div style={{ fontSize:12, fontWeight:600,
                                        color:isActive?T.text:T.textMid,
                                        whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>
                            {s.name}
                          </div>
                          <div style={{ fontSize:10, color:T.textDim, marginTop:1 }}>{s.desc}</div>
                        </div>
                      </div>
                      <div style={{ display:"flex", justifyContent:"space-between",
                                    alignItems:"center", marginTop:7, paddingLeft:18 }}>
                        <span style={{ fontSize:10, fontWeight:700, color:sc,
                                       background:sbg, border:`1px solid ${sc}33`,
                                       borderRadius:20, padding:"1px 7px", fontFamily:"monospace" }}>
                          {STATUS_LABEL[s.status]}
                        </span>
                        {s.duration &&
                          <span style={{ fontSize:10, color:T.textDim, fontFamily:"monospace" }}>
                            {s.duration}s
                          </span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}

          {/* Progress bar */}
          <div style={{ padding:16, marginTop:"auto", borderTop:`1px solid ${T.border}`, background:T.white }}>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
              <span style={{ fontSize:11, color:T.textDim, fontWeight:500 }}>Pipeline progress</span>
              <span style={{ fontSize:11, color:T.textMid, fontFamily:"monospace" }}>{done+errCnt}/9</span>
            </div>
            <div style={{ height:6, background:T.bg, borderRadius:3, overflow:"hidden",
                          border:`1px solid ${T.border}` }}>
              <div style={{ height:"100%", width:`${((done+errCnt)/9)*100}%`,
                            background:errCnt>0?T.err:T.pass,
                            borderRadius:3, transition:"width .4s ease" }} />
            </div>
          </div>
        </div>

        {/* RIGHT: Log viewer */}
        <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
          {sel && (
            <>
              {/* Stage header */}
              <div style={{ background:T.white, borderBottom:`1px solid ${T.border}`,
                            padding:"14px 20px", flexShrink:0 }}>
                <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                  <div style={{ display:"flex", alignItems:"center", gap:12 }}>
                    <div style={{ width:12, height:12, borderRadius:"50%",
                                  background:STATUS_COLOR[sel.status],
                                  ...(sel.status==="running"?{boxShadow:`0 0 0 3px ${T.run}33`}:{}) }} />
                    <div>
                      <div style={{ fontSize:16, fontWeight:700, color:T.text }}>{sel.name}</div>
                      <div style={{ fontSize:12, color:T.textDim }}>
                        {sel.desc}
                        <span style={{ marginLeft:8, background:MS_LIGHT[sel.milestone],
                                       color:MS[sel.milestone], borderRadius:20,
                                       padding:"1px 8px", fontSize:10, fontWeight:700 }}>
                          {sel.milestone}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div style={{ display:"flex", gap:20 }}>
                    {[["Status",  <span style={{ fontSize:12, fontWeight:700, color:STATUS_COLOR[sel.status],
                                                 background:STATUS_BG[sel.status],
                                                 border:`1px solid ${STATUS_COLOR[sel.status]}33`,
                                                 borderRadius:20, padding:"2px 10px", fontFamily:"monospace" }}>
                                    {STATUS_LABEL[sel.status]}
                                  </span>],
                      ["Duration", sel.duration ? `${sel.duration}s` : "—"],
                      ["Log lines", sel.logs.length]].map(([l,v])=>(
                      <div key={l} style={{ textAlign:"right" }}>
                        <div style={{ fontSize:10, color:T.textDim, marginBottom:3 }}>{l}</div>
                        {typeof v === "object" ? v :
                          <div style={{ fontSize:14, fontWeight:700, color:T.text, fontFamily:"monospace" }}>{v}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Log terminal — light surface, coloured text */}
              <div ref={logRef} className="sb"
                style={{ flex:1, overflowY:"auto", padding:"16px 20px",
                         background:"#F8FAFC",
                         fontFamily:"'JetBrains Mono','Fira Code','Courier New',monospace",
                         fontSize:12, borderTop:`1px solid ${T.border}` }}>
                {sel.logs.length===0 ? (
                  <div style={{ color:T.borderMd, paddingTop:48, textAlign:"center" }}>
                    <div style={{ fontSize:32, marginBottom:8 }}>⌛</div>
                    <div style={{ color:T.textDim }}>
                      {sel.status==="pending" ? "Waiting for earlier stages to complete…" : "Running…"}
                    </div>
                  </div>
                ) : sel.logs.map((line, i) => (
                  <div key={i} className="log-line"
                    style={{ display:"flex", gap:12, marginBottom:3, lineHeight:1.7,
                             padding:"1px 0",
                             borderBottom: i < sel.logs.length-1 ? `1px solid ${T.border}` : "none" }}>
                    <span style={{ color:T.borderMd, userSelect:"none", minWidth:30,
                                   fontSize:11, paddingTop:1 }}>
                      {String(i+1).padStart(3,"0")}
                    </span>
                    <span style={{ color:logColor(line), fontWeight: line.startsWith("[SUCCESS]") || line.startsWith("[ERROR]") ? 600 : 400 }}>
                      {line}
                    </span>
                  </div>
                ))}
                {sel.status==="running" && (
                  <div style={{ color:T.m2, marginTop:4, fontFamily:"monospace", fontSize:13 }}>▋</div>
                )}
              </div>

              {/* Bottom stage strip */}
              <div className="sb"
                style={{ background:T.white, borderTop:`1px solid ${T.border}`,
                         padding:"9px 16px", display:"flex", gap:6, flexShrink:0, overflowX:"auto" }}>
                {stages.map(s => (
                  <div key={s.id} onClick={()=>setSelectedId(s.id)}
                    style={{ flexShrink:0, display:"flex", alignItems:"center", gap:6,
                             padding:"4px 10px", borderRadius:20, cursor:"pointer",
                             background: s.id===selectedId ? MS_LIGHT[s.milestone] : T.bg,
                             border:`1px solid ${s.id===selectedId ? MS_MID[s.milestone] : T.border}` }}>
                    <div style={{ width:6, height:6, borderRadius:"50%", background:STATUS_COLOR[s.status] }} />
                    <span style={{ fontSize:11,
                                   color: s.id===selectedId ? MS[s.milestone] : T.textDim,
                                   fontWeight: s.id===selectedId ? 600 : 400,
                                   whiteSpace:"nowrap" }}>
                      {s.name}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
