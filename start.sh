#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# BVE Pipeline — Start Script  (Mac)
# WO-20260609-001  |  Webwise Technologies Pvt Ltd
# ─────────────────────────────────────────────────────────────────────────────
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT_DIR/backend"
FRONTEND="$ROOT_DIR/frontend"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  BIW Behavioural Validation Engine  WO-20260609-001  ${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Check .env ────────────────────────────────────────────────────────────────
if [ ! -f "$BACKEND/.env" ]; then
  echo -e "${YELLOW}⚙  backend/.env not found — creating a default one…${NC}"
  cat > "$BACKEND/.env" <<'EOF'
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=ollama3.2:3b
OLLAMA_TIMEOUT=120
EOF
  echo -e "${GREEN}✓  Wrote backend/.env with default Ollama settings${NC}"
fi

# Load OLLAMA_HOST / OLLAMA_MODEL from .env (fall back to defaults)
OLLAMA_HOST="$(grep -E '^OLLAMA_HOST=' "$BACKEND/.env" | cut -d '=' -f2-)"
OLLAMA_MODEL="$(grep -E '^OLLAMA_MODEL=' "$BACKEND/.env" | cut -d '=' -f2-)"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.1}"

# ── Check Ollama is installed ─────────────────────────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
  echo -e "${RED}✗  Ollama is not installed.${NC}"
  echo -e "   Install it from https://ollama.com/download, then re-run this script."
  exit 1
fi

# ── Check Ollama server is running ────────────────────────────────────────────
if ! curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  echo -e "${YELLOW}⚙  Ollama server not reachable at $OLLAMA_HOST — starting it…${NC}"
  ollama serve >/tmp/ollama.log 2>&1 &
  OLLAMA_PID=$!
  # Wait for it to come up
  for i in $(seq 1 15); do
    if curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo -e "${RED}✗  Ollama server failed to start. Check /tmp/ollama.log${NC}"
    exit 1
  fi
  echo -e "${GREEN}✓  Ollama server started (pid $OLLAMA_PID)${NC}"
else
  echo -e "${GREEN}✓  Ollama server already running at $OLLAMA_HOST${NC}"
fi

# ── Check the configured model is pulled ──────────────────────────────────────
if ! ollama list | awk '{print $1}' | grep -qx "$OLLAMA_MODEL" 2>/dev/null; then
  echo -e "${YELLOW}⚙  Model '$OLLAMA_MODEL' not found locally — pulling it (this may take a while)…${NC}"
  ollama pull "$OLLAMA_MODEL"
  echo -e "${GREEN}✓  Model '$OLLAMA_MODEL' pulled${NC}"
else
  echo -e "${GREEN}✓  Model '$OLLAMA_MODEL' already available${NC}"
fi

# ── Check venv ────────────────────────────────────────────────────────────────
if [ ! -d "$BACKEND/.venv" ]; then
  echo -e "${YELLOW}⚙  Creating Python virtual environment…${NC}"
  python3 -m venv "$BACKEND/.venv"
  source "$BACKEND/.venv/bin/activate"
  pip install -q -r "$BACKEND/requirements.txt"
  echo -e "${GREEN}✓  Backend dependencies installed${NC}"
else
  source "$BACKEND/.venv/bin/activate"
fi

# ── Check node_modules ────────────────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo -e "${YELLOW}⚙  Installing frontend dependencies…${NC}"
  cd "$FRONTEND" && npm install --silent
  echo -e "${GREEN}✓  Frontend dependencies installed${NC}"
fi

# ── Start backend ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}▶  Starting backend   → http://localhost:8000${NC}"
cd "$BACKEND"
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

sleep 2

# ── Start frontend ────────────────────────────────────────────────────────────
echo -e "${GREEN}▶  Starting frontend  → http://localhost:5173${NC}"
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Backend  : ${GREEN}http://localhost:8000${NC}"
echo -e "  Frontend : ${GREEN}http://localhost:5173${NC}"
echo -e "  API docs : ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  LLM      : ${GREEN}Ollama · $OLLAMA_MODEL · $OLLAMA_HOST${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Press Ctrl+C to stop both servers"
echo ""

# ── Cleanup on exit ───────────────────────────────────────────────────────────
trap "echo ''; echo 'Stopping servers…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait $BACKEND_PID $FRONTEND_PID