# Callwen Deploy Pipeline
# Usage:
#   make deploy      — full pipeline: lint → typecheck → test → push both remotes
#   make check       — lint + typecheck + test (no push)
#   make push        — push to both origin and vercel-deploy
#   make typecheck   — run tsc --noEmit
#   make test        — run backend pytest
#   make lint        — run frontend eslint
#   make hooks       — install pre-commit hooks

.PHONY: deploy check push typecheck test lint lint-backend hooks health

# ── Full pipeline ────────────────────────────────────────────────────────────

deploy: check push
	@echo ""
	@echo "Deploy complete. Railway and Vercel will pick up the push."

check: lint typecheck test
	@echo ""
	@echo "All checks passed."

# ── Individual steps ─────────────────────────────────────────────────────────

lint:
	@echo "→ Frontend lint..."
	cd frontend && npx next lint --quiet
	@echo "  Frontend lint passed."

typecheck:
	@echo "→ TypeScript typecheck..."
	cd frontend && npx tsc --noEmit
	@echo "  TypeScript typecheck passed."

test:
	@echo "→ Backend tests..."
	cd backend && venv/bin/python -m pytest tests/ -q --tb=short --ignore=tests/test_client_isolation.py
	@echo "  Backend tests passed."

push:
	@echo "→ Pushing to origin..."
	git push origin main
	@echo "→ Pushing to vercel-deploy..."
	git push vercel-deploy main
	@echo "  Both remotes updated."

# ── Health checks ────────────────────────────────────────────────────────────

health:
	@echo "→ Backend health..."
	@curl -sf https://callwen-backend-production.up.railway.app/health && echo "" || echo "  Backend unreachable"
	@echo "→ Frontend health..."
	@curl -sf https://callwen.com/api/health && echo "" || echo "  Frontend unreachable"

# ── Git hooks ────────────────────────────────────────────────────────────────

hooks:
	@echo "Installing pre-commit hook..."
	@cp scripts/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed. Runs tsc --noEmit before every commit."
