#!/bin/bash

PASS="✓ PASS"
FAIL="✗ FAIL"
BACKEND_DIR="$HOME/advisoryboard-mvp-code/backend"
FRONTEND_DIR="$HOME/advisoryboard-mvp-code/frontend"
OVERALL=0

echo ""
echo "========================================="
echo " AdvisoryBoard MVP - Environment Tests"
echo "========================================="

# ─────────────────────────────────────────────
# TEST 1: PostgreSQL Database
# ─────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────"
echo " TEST 1: PostgreSQL Database"
echo "─────────────────────────────────────────"

if ! command -v psql &>/dev/null; then
  echo " $FAIL — psql not found in PATH"
  OVERALL=1
else
  PG_RESULT=$(psql -d advisoryboard_dev -c "SELECT version();" -t 2>&1)
  if echo "$PG_RESULT" | grep -q "PostgreSQL"; then
    PG_VERSION=$(echo "$PG_RESULT" | grep -o "PostgreSQL [0-9.]*" | head -1)
    echo " $PASS — Connected to advisoryboard_dev"
    echo "         Version: $PG_VERSION"
  else
    echo " $FAIL — Could not connect to advisoryboard_dev"
    echo "         Error: $PG_RESULT"
    OVERALL=1
  fi
fi

# ─────────────────────────────────────────────
# TEST 2: FastAPI Backend Server
# ─────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────"
echo " TEST 2: FastAPI Backend Server"
echo "─────────────────────────────────────────"

cd "$BACKEND_DIR"
source venv/bin/activate

# Install openai if not present (needed for Test 4)
if ! python -c "import openai" &>/dev/null; then
  echo " Installing openai package..."
  pip install openai --quiet
fi

uvicorn main:app --port 8000 &
UVICORN_PID=$!
sleep 5

API_RESULT=$(curl -s http://localhost:8000 2>&1)
if echo "$API_RESULT" | grep -q "AdvisoryBoard API is running"; then
  echo " $PASS — FastAPI server running on port 8000"
  echo "         Response: $API_RESULT"
  # Also test /health endpoint
  HEALTH=$(curl -s http://localhost:8000/health)
  echo "         Health:   $HEALTH"
else
  echo " $FAIL — Could not reach http://localhost:8000"
  echo "         Response: $API_RESULT"
  OVERALL=1
fi

kill $UVICORN_PID 2>/dev/null
wait $UVICORN_PID 2>/dev/null
echo "         Server stopped."

deactivate

# ─────────────────────────────────────────────
# TEST 3: Next.js Frontend Server
# ─────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────"
echo " TEST 3: Next.js Frontend Server"
echo "─────────────────────────────────────────"

cd "$FRONTEND_DIR"
npm run dev &
NEXT_PID=$!
sleep 12

NEXT_RESULT=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>&1)
if [ "$NEXT_RESULT" = "200" ]; then
  echo " $PASS — Next.js server running on port 3000"
  echo "         HTTP status: 200 OK"
else
  echo " $FAIL — Could not reach http://localhost:3000"
  echo "         HTTP status: $NEXT_RESULT"
  OVERALL=1
fi

kill $NEXT_PID 2>/dev/null
wait $NEXT_PID 2>/dev/null
echo "         Server stopped."

# ─────────────────────────────────────────────
# TEST 4: OpenAI API Connection
# ─────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────"
echo " TEST 4: OpenAI API Connection"
echo "─────────────────────────────────────────"

cd "$BACKEND_DIR"
source venv/bin/activate

# Write test script
cat > /tmp/test_openai.py << PYEOF
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv("$BACKEND_DIR/.env.local")

api_key = os.getenv('OPENAI_API_KEY')
if not api_key or api_key == 'your-openai-api-key-here':
    print("MISSING_KEY")
else:
    client = OpenAI(api_key=api_key)
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input="test"
        )
        print(f"SUCCESS:{len(response.data[0].embedding)}")
    except Exception as e:
        print(f"ERROR:{e}")
PYEOF

OPENAI_RESULT=$(python /tmp/test_openai.py 2>&1)

if echo "$OPENAI_RESULT" | grep -q "MISSING_KEY"; then
  echo " ⚠ SKIP — OPENAI_API_KEY not set in backend/.env.local"
  echo "           Add your key to: $BACKEND_DIR/.env.local"
  echo "           Then re-run this test"
elif echo "$OPENAI_RESULT" | grep -q "SUCCESS:"; then
  DIMS=$(echo "$OPENAI_RESULT" | grep -o "SUCCESS:[0-9]*" | cut -d: -f2)
  echo " $PASS — OpenAI API connected successfully"
  echo "         Model: text-embedding-3-small"
  echo "         Embedding dimensions: $DIMS"
else
  echo " $FAIL — OpenAI API error"
  echo "         Error: $OPENAI_RESULT"
  OVERALL=1
fi

deactivate
rm -f /tmp/test_openai.py

# ─────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo " FINAL SUMMARY"
echo "========================================="

if [ $OVERALL -eq 0 ]; then
  echo " Overall Status: ALL TESTS PASSED ✓"
  echo " Development environment is ready."
else
  echo " Overall Status: SOME TESTS FAILED ✗"
  echo " Review failures above before proceeding."
fi
echo "========================================="
echo ""
