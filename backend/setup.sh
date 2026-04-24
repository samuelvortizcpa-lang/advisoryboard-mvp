#!/bin/bash
set -e

echo "========================================="
echo " AdvisoryBoard Backend Setup"
echo "========================================="

# Step 1: Check Python version
echo ""
echo "[1/5] Checking Python version..."
PYTHON=$(command -v python3.11 || command -v python3.12 || command -v python3 || echo "")

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python not found. Please install Python 3.11+."
  exit 1
fi

VERSION=$($PYTHON --version 2>&1)
MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]; }; then
  echo "ERROR: Python 3.11+ required. Found: $VERSION"
  exit 1
fi

echo "OK: $VERSION ($PYTHON)"

# Step 2: Create virtual environment
echo ""
echo "[2/5] Creating virtual environment 'venv'..."
if [ -d "venv" ]; then
  echo "INFO: 'venv' already exists, skipping creation."
else
  $PYTHON -m venv venv
  echo "OK: venv created."
fi

# Step 3: Activate virtual environment
echo ""
echo "[3/5] Activating virtual environment..."
source venv/bin/activate
echo "OK: venv activated. ($(which python))"

# Step 4: Install dependencies
echo ""
echo "[4/5] Installing packages from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo "OK: All packages installed."

# Step 5: Copy .env.example to .env.local
echo ""
echo "[5/5] Creating .env.local from .env.example..."
if [ -f ".env.local" ]; then
  echo "INFO: .env.local already exists, skipping."
else
  cp .env.example .env.local
  echo "OK: .env.local created."
fi

# Report: list installed packages
echo ""
echo "========================================="
echo " Installed Packages"
echo "========================================="
pip list

echo ""
echo "========================================="
echo " Setup Complete!"
echo "========================================="
echo ""
echo "To activate the venv in future sessions:"
echo "  source ~/advisoryboard-mvp-code/backend/venv/bin/activate"
echo ""
echo "To start the API server:"
echo "  uvicorn main:app --reload"
echo ""
