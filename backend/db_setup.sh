#!/bin/bash
set -e

echo "========================================="
echo " AdvisoryBoard Database Setup"
echo "========================================="

DB_NAME="advisoryboard_dev"

# Step 1: Check if PostgreSQL is installed
echo ""
echo "[1/5] Checking PostgreSQL installation..."
if ! command -v psql &> /dev/null; then
  echo ""
  echo "ERROR: PostgreSQL (psql) is not installed or not in PATH."
  echo ""
  echo "To install PostgreSQL 15+ on macOS with Homebrew:"
  echo "  brew install postgresql@15"
  echo "  brew services start postgresql@15"
  echo "  echo 'export PATH=\"/opt/homebrew/opt/postgresql@15/bin:\$PATH\"' >> ~/.zshrc"
  echo "  source ~/.zshrc"
  echo ""
  exit 1
fi

PSQL_VERSION=$(psql --version)
echo "OK: $PSQL_VERSION"

# Check version is 15+
VERSION_NUM=$(psql --version | grep -oE '[0-9]+' | head -1)
if [ "$VERSION_NUM" -lt 15 ]; then
  echo "WARNING: PostgreSQL $VERSION_NUM detected. Version 15+ is required."
  echo "Please upgrade: brew upgrade postgresql@15"
  exit 1
fi

# Step 2: Check if PostgreSQL server is running
echo ""
echo "[2/5] Checking if PostgreSQL server is running..."
if pg_isready -q; then
  echo "OK: PostgreSQL server is ready and accepting connections."
else
  echo "ERROR: PostgreSQL server is not running."
  echo ""
  echo "Start it with:"
  echo "  brew services start postgresql@15"
  echo "  (or: brew services start postgresql)"
  exit 1
fi

# Step 3: Create database (skip if exists)
echo ""
echo "[3/5] Creating database '$DB_NAME'..."
if psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
  echo "INFO: Database '$DB_NAME' already exists. Skipping creation."
else
  createdb "$DB_NAME"
  echo "OK: Database '$DB_NAME' created."
fi

# Step 4: Install pgvector extension
echo ""
echo "[4/5] Setting up pgvector extension..."
PGVECTOR_CHECK=$(psql -d "$DB_NAME" -tAc "SELECT COUNT(*) FROM pg_available_extensions WHERE name = 'vector';" 2>/dev/null || echo "0")

if [ "$PGVECTOR_CHECK" = "0" ] || [ "$PGVECTOR_CHECK" = "" ]; then
  echo "WARNING: pgvector is not installed on this system."
  echo ""
  echo "To install pgvector:"
  echo "  brew install pgvector"
  echo "  (then re-run this script)"
  echo ""
  echo "Continuing without pgvector..."
  PGVECTOR_INSTALLED=false
else
  psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null 2>&1
  echo "OK: pgvector extension enabled in '$DB_NAME'."
  PGVECTOR_INSTALLED=true
fi

# Step 5: Test connection and run verification queries
echo ""
echo "[5/5] Running verification queries..."
echo ""
echo "--- PostgreSQL Version ---"
psql -d "$DB_NAME" -c "SELECT version();"

echo ""
echo "--- pgvector Extension Status ---"
psql -d "$DB_NAME" -c "SELECT name, default_version, installed_version, comment FROM pg_available_extensions WHERE name = 'vector';"

# Final report
echo ""
echo "========================================="
echo " Setup Report"
echo "========================================="
echo " Database name   : $DB_NAME"
echo " PostgreSQL      : $PSQL_VERSION"
if [ "$PGVECTOR_INSTALLED" = true ]; then
  echo " pgvector        : INSTALLED & ENABLED"
else
  echo " pgvector        : NOT INSTALLED (see instructions above)"
fi
echo ""
echo " Connection test : psql -d $DB_NAME -c \"SELECT 1;\""
psql -d "$DB_NAME" -c "SELECT 1 AS connection_test;"
echo ""
echo "========================================="
echo " Database Setup Complete!"
echo "========================================="
echo ""
echo "Connection string for .env.local:"
echo "  DATABASE_URL=postgresql://localhost:5432/$DB_NAME"
echo ""
