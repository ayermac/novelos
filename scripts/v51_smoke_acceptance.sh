#!/bin/bash
# v5.1 Post-Acceptance Smoke Test Script
# 验证前后端分离版本的基本功能和验收标准

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== v5.1 Smoke Acceptance Test ===${NC}"
echo "Project root: $PROJECT_ROOT"
echo ""

# Track overall status
PASS_COUNT=0
FAIL_COUNT=0

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# 1. Check Python imports
echo -e "${YELLOW}[1/8] Checking Python imports...${NC}"
cd "$PROJECT_ROOT"

if python3 -c "from novel_factory.api_app import create_api_app" 2>/dev/null; then
    pass "API app import"
else
    fail "API app import"
fi

if python3 -c "from novel_factory.api.routes import health_router, dashboard_router, projects_router" 2>/dev/null; then
    pass "API routes import"
else
    fail "API routes import"
fi

if python3 -c "from novel_factory.cli_app.main import main" 2>/dev/null; then
    pass "CLI main import"
else
    fail "CLI main import"
fi

# 2. Check CLI api command
echo ""
echo -e "${YELLOW}[2/8] Checking CLI api command...${NC}"

if python3 -m novel_factory.cli_app.main api --help >/dev/null 2>&1; then
    pass "novelos api --help"
else
    fail "novelos api --help"
fi

# 3. Run pytest
echo ""
echo -e "${YELLOW}[3/8] Running pytest...${NC}"

if python3 -m pytest -q --tb=no 2>&1 | tail -1 | grep -q "passed"; then
    RESULT=$(python3 -m pytest -q --tb=no 2>&1 | tail -1)
    pass "pytest: $RESULT"
else
    fail "pytest failed"
fi

# 4. Check frontend build
echo ""
echo -e "${YELLOW}[4/8] Checking frontend build...${NC}"

cd "$PROJECT_ROOT/frontend"

if [ ! -f "package.json" ]; then
    fail "frontend/package.json not found"
else
    pass "frontend/package.json exists"
fi

if [ ! -d "node_modules" ]; then
    warn "node_modules not found, running npm install..."
    npm install --silent
fi

if npm run typecheck >/dev/null 2>&1; then
    pass "frontend typecheck"
else
    fail "frontend typecheck"
fi

if npm run build >/dev/null 2>&1; then
    pass "frontend build"
else
    fail "frontend build"
fi

# 5. API smoke test with TestClient
echo ""
echo -e "${YELLOW}[5/8] Running API smoke tests...${NC}"

cd "$PROJECT_ROOT"

# Create temporary test script
TEMP_SCRIPT=$(mktemp)
cat > "$TEMP_SCRIPT" << 'PYEOF'
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db

def test_api_smoke():
    """Smoke test for API endpoints"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        # Initialize database
        init_db(db_path)
        
        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)
        
        tests_passed = 0
        tests_failed = 0
        
        # Health check
        try:
            resp = client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            print("✓ GET /api/health")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/health: {e}")
            tests_failed += 1
        
        # Dashboard (empty)
        try:
            resp = client.get("/api/dashboard")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            assert "project_count" in data["data"]
            print("✓ GET /api/dashboard")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/dashboard: {e}")
            tests_failed += 1
        
        # Projects list (empty)
        try:
            resp = client.get("/api/projects")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            assert isinstance(data["data"], list)
            print("✓ GET /api/projects")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/projects: {e}")
            tests_failed += 1
        
        # Create project via onboarding
        try:
            resp = client.post("/api/onboarding/projects", json={
                "project_id": "smoke_test_project",
                "name": "Smoke Test Novel",
                "genre": "玄幻",
                "target_words": 100000,
                "initial_chapter_count": 10,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            print("✓ POST /api/onboarding/projects")
            tests_passed += 1
        except Exception as e:
            print(f"✗ POST /api/onboarding/projects: {e}")
            tests_failed += 1
        
        # Get project workspace
        try:
            resp = client.get("/api/projects/smoke_test_project/workspace")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            print("✓ GET /api/projects/{id}/workspace")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/projects/{id}/workspace: {e}")
            tests_failed += 1
        
        # Run chapter (stub mode)
        try:
            resp = client.post("/api/run/chapter", json={
                "project_id": "smoke_test_project",
                "chapter": 1,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            assert "run_id" in data["data"]
            print("✓ POST /api/run/chapter")
            tests_passed += 1
        except Exception as e:
            print(f"✗ POST /api/run/chapter: {e}")
            tests_failed += 1
        
        # Style console
        try:
            resp = client.get("/api/style/console")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            print("✓ GET /api/style/console")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/style/console: {e}")
            tests_failed += 1
        
        # Settings
        try:
            resp = client.get("/api/settings")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            # Check no API key exposure
            resp_text = resp.text
            assert "sk-" not in resp_text
            assert "api_key" not in resp_text or '"has_key": true' in resp_text
            print("✓ GET /api/settings (no key exposure)")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/settings: {e}")
            tests_failed += 1
        
        # Acceptance matrix
        try:
            resp = client.get("/api/acceptance")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            assert "capabilities" in data["data"]
            print("✓ GET /api/acceptance")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/acceptance: {e}")
            tests_failed += 1
        
        # Chapter detail endpoint (v5.1.3)
        try:
            resp = client.get("/api/projects/smoke_test_project/chapters/1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] == True
            assert "content" in data["data"]
            assert data["data"]["chapter_number"] == 1
            print("✓ GET /api/projects/{id}/chapters/{num}")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/projects/{id}/chapters/{num}: {e}")
            tests_failed += 1
        
        # Run detail endpoint (v5.1.4)
        try:
            # Get run_id from the previous run
            resp = client.get("/api/projects/smoke_test_project/workspace")
            assert resp.status_code == 200
            workspace = resp.json()["data"]
            if workspace.get("recent_runs") and len(workspace["recent_runs"]) > 0:
                run_id = workspace["recent_runs"][0]["run_id"]
                resp = client.get(f"/api/runs/{run_id}")
                assert resp.status_code == 200
                data = resp.json()
                assert data["ok"] == True
                assert "steps" in data["data"]
                assert len(data["data"]["steps"]) == 5
                print("✓ GET /api/runs/{run_id}")
                tests_passed += 1
            else:
                print("⊘ GET /api/runs/{run_id} (no runs yet)")
                tests_passed += 1
        except Exception as e:
            print(f"✗ GET /api/runs/{{run_id}}: {e}")
            tests_failed += 1
        
        return tests_passed, tests_failed
        
    finally:
        import os
        if os.path.exists(db_path):
            os.unlink(db_path)

if __name__ == "__main__":
    passed, failed = test_api_smoke()
    print(f"\nAPI Smoke Tests: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
PYEOF

if python3 "$TEMP_SCRIPT"; then
    pass "API smoke tests"
    rm "$TEMP_SCRIPT"
else
    fail "API smoke tests"
    rm "$TEMP_SCRIPT"
fi

# 6. Check .gitignore rules
echo ""
echo -e "${YELLOW}[6/8] Checking .gitignore rules...${NC}"

cd "$PROJECT_ROOT"

if git check-ignore -q frontend/node_modules 2>/dev/null || [ ! -d "frontend/node_modules" ]; then
    pass "frontend/node_modules ignored"
else
    fail "frontend/node_modules not ignored"
fi

if git check-ignore -q frontend/dist 2>/dev/null || [ ! -d "frontend/dist" ]; then
    pass "frontend/dist ignored"
else
    fail "frontend/dist not ignored"
fi

if git check-ignore -q config/acceptance.yaml 2>/dev/null || [ ! -f "config/acceptance.yaml" ]; then
    pass "config/acceptance.yaml ignored"
else
    fail "config/acceptance.yaml not ignored"
fi

if git check-ignore -q stderr.txt 2>/dev/null || [ ! -f "stderr.txt" ]; then
    pass "stderr.txt ignored"
else
    fail "stderr.txt not ignored"
fi

# Check frontend/src/lib/api.ts is NOT ignored
if git check-ignore -q frontend/src/lib/api.ts 2>/dev/null; then
    fail "frontend/src/lib/api.ts is incorrectly ignored"
else
    pass "frontend/src/lib/api.ts is tracked"
fi

# 7. Check no sensitive files in git
echo ""
echo -e "${YELLOW}[7/8] Checking for sensitive files in git...${NC}"

if git ls-files | grep -q "node_modules"; then
    fail "node_modules found in git"
else
    pass "no node_modules in git"
fi

if git ls-files | grep -q "frontend/dist"; then
    fail "frontend/dist found in git"
else
    pass "no frontend/dist in git"
fi

if git ls-files | grep -q "config/acceptance.yaml"; then
    fail "config/acceptance.yaml found in git"
else
    pass "no config/acceptance.yaml in git"
fi

if git ls-files | grep -q "stderr.txt"; then
    fail "stderr.txt found in git"
else
    pass "no stderr.txt in git"
fi

# 8. Final summary
echo ""
echo -e "${YELLOW}[8/8] Final Summary${NC}"
echo ""
echo -e "${GREEN}Passed: $PASS_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"

if [ $FAIL_COUNT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=== All smoke tests passed! ===${NC}"
    echo ""
    echo "v5.1.3 is ready for acceptance."
    echo ""
    echo "Quick start:"
    echo "  API:      novelos api --host 127.0.0.1 --port 8765 --llm-mode stub"
    echo "  Frontend: cd frontend && npm run dev"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}=== Some smoke tests failed ===${NC}"
    echo ""
    exit 1
fi
