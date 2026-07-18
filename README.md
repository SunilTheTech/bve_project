# BIW Behavioural Validation Engine
**Work Order:** WO-20260609-001  
**Client:** DIGITALTRANSOLS AI PRIVATE LIMITED (Digitran)  
**Service Provider:** Webwise Technologies Pvt Ltd — Sunil Bhakuni

---

## What This Is

A full-stack application that:
1. Accepts an **Excel / CSV file** from the browser
2. Uses **Claude AI** to convert it into a BIW Knowledge Graph JSON
3. Runs the KG through a **9-stage validation pipeline** (Python + NetworkX)
4. Shows live stage-by-stage logs on a **real-time dashboard**

---

## Project Structure

```
bve_project/
├── backend/                        Python FastAPI backend
│   ├── main.py                     API server + Anthropic integration
│   ├── requirements.txt
│   ├── .env.example                Copy to .env, add your API key
│   ├── data/sample_kg.json         Bundled geo-station fixture
│   ├── models/kg_models.py         Pydantic data models
│   ├── kg_parser/parser.py         KG Parser Module           (Sprint 1)
│   ├── graph/
│   │   ├── execution_graph_builder.py  Graph Builder          (Sprint 1)
│   │   └── graph_validator.py          Graph Validator        (Sprint 1)
│   ├── engine/
│   │   ├── dependency_resolver.py  Topological ordering       (Sprint 2)
│   │   ├── timing_scheduler.py     Resource-aware scheduling  (Sprint 2)
│   │   ├── simulation_engine.py    Virtual clock + states     (Sprint 2)
│   │   └── scenario_generator.py   DFS/BFS scenarios          (Sprint 3)
│   ├── validation/
│   │   └── validation_engine.py    7-category checks          (Sprint 3)
│   ├── reporting/
│   │   └── reporting_layer.py      JSON/TXT reports           (Sprint 3)
│   └── tests/
│       └── test_pipeline.py        25 pytest cases
├── frontend/                       React + Vite dashboard
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       └── App.jsx                 Upload screen + Dashboard
├── start.sh                        One-command startup (Mac/Linux)
└── README.md
```

---

## Mac Setup — Step by Step

### Prerequisites

Open **Terminal** (Cmd + Space → type "Terminal" → Enter).

---

### Step 1 — Install Homebrew

Homebrew is the Mac package manager. Skip if already installed.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Verify:
```bash
brew --version
```

---

### Step 2 — Install Python 3.11

```bash
brew install python@3.11
```

Verify:
```bash
python3.11 --version
# Expected: Python 3.11.x
```

---

### Step 3 — Install Node.js 20

```bash
brew install node@20
```

If node is not found after install, add it to your PATH:
```bash
echo 'export PATH="/opt/homebrew/opt/node@20/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Verify:
```bash
node --version    # Expected: v20.x.x
npm  --version    # Expected: 10.x.x
```

---

### Step 4 — Unzip the Project

```bash
cd ~/Downloads
unzip bve_project.zip -d bve_project
cd bve_project
```

---

### Step 5 — Get an Anthropic API Key

1. Go to **https://console.anthropic.com**
2. Sign in (or create a free account)
3. Click **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-…`)

---

### Step 6 — Configure the Backend

```bash
cd backend
cp .env.example .env
```

Open `.env` in any editor and paste your key:

```bash
# using nano (simple terminal editor)
nano .env
```

Change this line:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
to your real key. Save with **Ctrl+O → Enter → Ctrl+X**.

---

### Step 7 — Install Backend Dependencies

```bash
# Still inside backend/
python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Expected output ends with: `Successfully installed ...`

---

### Step 8 — Run Backend Tests (optional but recommended)

```bash
# Still inside backend/ with .venv active
pytest tests/ -v
```

Expected: `25 passed in X.Xs`

---

### Step 9 — Install Frontend Dependencies

Open a **new Terminal tab** (Cmd+T):

```bash
cd ~/Downloads/bve_project/frontend
npm install
```

---

### Step 10 — Start Both Servers

**Option A — One command (recommended):**

```bash
cd ~/Downloads/bve_project
chmod +x start.sh
./start.sh
```

**Option B — Two separate terminals:**

Terminal 1 (backend):
```bash
cd ~/Downloads/bve_project/backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2 (frontend):
```bash
cd ~/Downloads/bve_project/frontend
npm run dev
```

---

### Step 11 — Open the Dashboard

Open your browser and go to:

```
http://localhost:5173
```

The green dot in the header confirms the backend is connected.

---

## Using the Application

### Upload Screen
1. Drag and drop any Excel (`.xlsx`), CSV, or use the sample KG
2. Click **Build KG** — Claude converts your data to a Knowledge Graph
3. Click **Run Pipeline** — all 9 stages execute with live logs

### Dashboard
- Left panel: 9 pipeline stages grouped by sprint milestone
- Click any stage to view its real-time log output
- Stats bar shows: events, edges, violations, virtual time, coverage

### Test with the bundled sample
```bash
curl http://localhost:8000/api/simulate/sample | python3 -m json.tool | head -40
```

---

## API Endpoints

| Method | URL                       | Description                              |
|--------|---------------------------|------------------------------------------|
| GET    | `/healthz`                | Liveness probe                           |
| POST   | `/api/convert-to-kg`      | Convert Excel rows → KG JSON via Claude  |
| POST   | `/api/simulate`           | Run full 9-stage pipeline on a KG        |
| GET    | `/api/simulate/sample`    | Run on bundled geo-station fixture       |
| GET    | `/docs`                   | Interactive Swagger UI                   |

---

## Stopping the Servers

Press **Ctrl+C** in the terminal where `start.sh` is running.

Or stop each individually:
```bash
# find and kill backend
lsof -ti:8000 | xargs kill -9

# find and kill frontend
lsof -ti:5173 | xargs kill -9
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `command not found: python3.11` | Run `brew install python@3.11` |
| `command not found: node` | Run `brew install node@20` and add to PATH (Step 3) |
| Backend green dot is red | Check uvicorn is running on port 8000; check `.env` has valid API key |
| `pip install` fails | Make sure `.venv` is activated: `source .venv/bin/activate` |
| Port 8000 already in use | `lsof -ti:8000 | xargs kill -9` then restart |
| Port 5173 already in use | `lsof -ti:5173 | xargs kill -9` then restart |
| Claude API errors | Verify `ANTHROPIC_API_KEY` in `backend/.env` is correct |

---

## Running Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

25 tests covering: KG parsing, graph construction, graph validation,
dependency resolution, simulation engine, validation engine (7 categories),
DFS/BFS scenario generation, and end-to-end pipeline.

---

## Milestone Reference (WO Section 4)

| Milestone | Weeks | Modules                                            | Payment     |
|-----------|-------|----------------------------------------------------|-------------|
| M1        | 1–2   | KG Parser, Graph Builder, Graph Validator          | Rs. 25,000  |
| M2        | 3–4   | Dependency Resolver, Scheduler, Simulation Engine  | Rs. 25,000  |
| M3        | 5–6   | Validation Engine, DFS/BFS, Reporting, Deployment  | Rs. 25,000  |
