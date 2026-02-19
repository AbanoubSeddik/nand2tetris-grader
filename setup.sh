#!/usr/bin/env bash

echo ""
echo "═══════════════════════════════════════════════"
echo "  nand2tetris Auto-Grader — Setup & Verify"
echo "═══════════════════════════════════════════════"
echo ""

ERRORS=0
WARNINGS=0

# ── Helper functions ─────────────────────────────────────────
ok()   { echo "  ✅  $1"; }
warn() { echo "  ⚠️   $1"; WARNINGS=$((WARNINGS + 1)); }
fail() { echo "  ❌  $1"; ERRORS=$((ERRORS + 1)); }
info() { echo "  ℹ️   $1"; }

# ── 1. Check Docker ──────────────────────────────────────────
echo "── Docker ──────────────────────────────────────"
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null | head -1)
    ok "Docker found: $DOCKER_VERSION"

    if docker info &>/dev/null; then
        ok "Docker daemon is running"
    else
        fail "Docker is installed but daemon is not running"
        info "Start Docker Desktop or run: sudo systemctl start docker"
    fi
else
    fail "Docker not found"
    info "Install from https://docs.docker.com/get-docker/"
fi

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    ok "Docker Compose available"
else
    fail "Docker Compose not found"
    info "Comes with Docker Desktop, or install: docker-compose-plugin"
fi
echo ""

# ── 2. Check .env ────────────────────────────────────────────
echo "── Configuration (.env) ─────────────────────────"
if [ -f ".env" ]; then
    ok ".env file exists"

    # Check each required variable
    for VAR in MOODLE_URL MOODLE_TOKEN TELEGRAM_TOKEN GEMINI_API_KEY ALLOWED_USER_IDS; do
        VALUE=$(grep "^${VAR}=" .env 2>/dev/null | cut -d'=' -f2-)
        if [ -z "$VALUE" ]; then
            fail "$VAR is missing or empty"
        elif echo "$VALUE" | grep -qi "paste_\|your_\|_here"; then
            fail "$VAR still has placeholder value — replace with your real key"
        else
            # Mask the value for display
            MASKED="${VALUE:0:4}...${VALUE: -4}"
            ok "$VAR is set ($MASKED)"
        fi
    done

    # Check optional variables
    DG=$(grep "^DEFAULT_GROUP=" .env 2>/dev/null | cut -d'=' -f2-)
    if [ -n "$DG" ]; then
        ok "DEFAULT_GROUP = $DG"
    else
        warn "DEFAULT_GROUP not set (will show group picker each time)"
    fi

else
    fail ".env file not found"
    info "Create it: cp .env.example .env && nano .env"
fi
echo ""

# ── 3. Check .env.example ───────────────────────────────────
echo "── Template (.env.example) ──────────────────────"
if [ -f ".env.example" ]; then
    ok ".env.example exists (for other TAs)"
else
    warn ".env.example missing — other TAs won't have a template"
    info "Create one with placeholder values"
fi
echo ""

# ── 4. Check nand2tetris tools ───────────────────────────────
echo "── nand2tetris Tools ────────────────────────────"
TOOLS_BASE="tools/nand2tetris/tools"

if [ -d "$TOOLS_BASE" ]; then
    ok "Tools directory exists: $TOOLS_BASE"
else
    fail "Tools directory missing: $TOOLS_BASE"
    info "Download from https://www.nand2tetris.org/software"
    info "Then: unzip nand2tetris.zip -d /tmp/n2t"
    info "      mkdir -p tools/nand2tetris"
    info "      cp -r /tmp/n2t/nand2tetris/tools tools/nand2tetris/"
fi

# Check each simulator
for SIM in HardwareSimulator CPUEmulator VMEmulator TextComparer; do
    SH_FILE="$TOOLS_BASE/${SIM}.sh"
    BAT_FILE="$TOOLS_BASE/${SIM}.bat"
    if [ -f "$SH_FILE" ]; then
        if [ -x "$SH_FILE" ]; then
            ok "$SIM.sh found and executable"
        else
            warn "$SIM.sh found but not executable"
            info "Fix: chmod +x $SH_FILE"
        fi
    elif [ -f "$BAT_FILE" ]; then
        warn "$SIM.sh missing but .bat exists (Linux/Mac needs .sh)"
        info "The nand2tetris download should include .sh files"
    else
        if [ "$SIM" = "HardwareSimulator" ] || [ "$SIM" = "CPUEmulator" ]; then
            fail "$SIM not found (required for grading)"
        else
            warn "$SIM not found (optional)"
        fi
    fi
done

# Check builtInChips
if [ -d "$TOOLS_BASE/builtInChips" ]; then
    BUILTIN_COUNT=$(ls "$TOOLS_BASE/builtInChips/"*.hdl 2>/dev/null | wc -l | tr -d ' ')
    ok "builtInChips directory found ($BUILTIN_COUNT chips)"
else
    warn "builtInChips directory missing — some tests may fail"
fi

# Check for Java classes / jars
JAR_COUNT=$(find "$TOOLS_BASE" -name "*.jar" 2>/dev/null | wc -l | tr -d ' ')
CLASS_COUNT=$(find "$TOOLS_BASE" -name "*.class" 2>/dev/null | wc -l | tr -d ' ')
if [ "$JAR_COUNT" -gt 0 ] || [ "$CLASS_COUNT" -gt 0 ]; then
    ok "Java binaries found ($JAR_COUNT jars, $CLASS_COUNT classes)"
else
    if [ -d "$TOOLS_BASE" ]; then
        warn "No .jar or .class files found in tools — simulators may not work"
    fi
fi
echo ""

# ── 5. Check test files per project ─────────────────────────
echo "── Test Files ─────────────────────────────────────"

declare -A PROJECT_EXPECTED
PROJECT_EXPECTED[project01]=15
PROJECT_EXPECTED[project02]=6
PROJECT_EXPECTED[project03]=8
PROJECT_EXPECTED[project04]=2
PROJECT_EXPECTED[project05]=3

TOTAL_TST=0
TOTAL_CMP=0

if [ -d "grader_test_files" ]; then
    ok "grader_test_files/ directory exists"

    for PROJ_DIR in project01 project02 project03 project04 project05; do
        DIR="grader_test_files/$PROJ_DIR"
        EXPECTED=${PROJECT_EXPECTED[$PROJ_DIR]:-0}

        if [ -d "$DIR" ]; then
            TST=$(ls "$DIR"/*.tst 2>/dev/null | wc -l | tr -d ' ')
            CMP=$(ls "$DIR"/*.cmp 2>/dev/null | wc -l | tr -d ' ')
            TOTAL_TST=$((TOTAL_TST + TST))
            TOTAL_CMP=$((TOTAL_CMP + CMP))

            if [ "$TST" -ge "$EXPECTED" ]; then
                ok "$PROJ_DIR: $TST .tst, $CMP .cmp (expected >= $EXPECTED)"
            else
                warn "$PROJ_DIR: only $TST/$EXPECTED .tst files"
                info "Copy from nand2tetris download"
            fi

            # Check for mismatched .tst without .cmp
            for TST_FILE in "$DIR"/*.tst; do
                [ -f "$TST_FILE" ] || continue
                BASE=$(basename "$TST_FILE" .tst)
                if [ ! -f "$DIR/${BASE}.cmp" ]; then
                    warn "$PROJ_DIR/${BASE}.tst has no matching .cmp file"
                fi
            done
        else
            if [ "$PROJ_DIR" = "project01" ]; then
                fail "$DIR/ missing (required for HW1)"
            else
                warn "$DIR/ missing (needed when grading this project)"
            fi
        fi
    done

    # Check for old flat structure (files directly in grader_test_files/)
    FLAT_TST=$(ls grader_test_files/*.tst 2>/dev/null | wc -l | tr -d ' ')
    if [ "$FLAT_TST" -gt 0 ]; then
        warn "Found $FLAT_TST .tst files directly in grader_test_files/"
        info "These should be in subdirectories (project01/, project02/, etc.)"
        info "Move them: mv grader_test_files/*.tst grader_test_files/project01/"
        info "           mv grader_test_files/*.cmp grader_test_files/project01/"
    fi
else
    fail "grader_test_files/ directory missing"
    info "Create it: mkdir -p grader_test_files/project01"
fi

echo ""
echo "  Total: $TOTAL_TST .tst files, $TOTAL_CMP .cmp files"
echo ""

# ── 6. Check Python files ───────────────────────────────────
echo "── Application Files ────────────────────────────"
ALL_PY_OK=true
for PY_FILE in bot.py config.py moodle_client.py grading_engine.py ai_report.py database.py; do
    if [ -f "$PY_FILE" ]; then
        # Quick syntax check
        if python3 -c "import ast; ast.parse(open('$PY_FILE').read())" 2>/dev/null; then
            ok "$PY_FILE (syntax OK)"
        else
            fail "$PY_FILE has syntax errors"
            ALL_PY_OK=false
        fi
    else
        fail "$PY_FILE missing"
        ALL_PY_OK=false
    fi
done
echo ""

# ── 6b. Check archive extractors ────────────────────────────
echo "── Archive Extractors ───────────────────────────"
if command -v unrar >/dev/null 2>&1; then
    ok "unrar found (RAR extraction supported)"
elif command -v unar >/dev/null 2>&1; then
    ok "unar found (RAR extraction supported)"
elif command -v bsdtar >/dev/null 2>&1; then
    ok "bsdtar found (RAR extraction supported)"
else
    warn "No RAR extractor found (unrar/unar/bsdtar)"
    info "RAR submissions will fail to extract until one is installed"
fi
echo ""

# ── 7. Check Docker files ───────────────────────────────────
echo "── Docker Files ───────────────────────────────────"
for DFILE in Dockerfile docker-compose.yml requirements.txt; do
    if [ -f "$DFILE" ]; then
        ok "$DFILE exists"
    else
        fail "$DFILE missing"
    fi
done

if [ -f ".dockerignore" ]; then
    ok ".dockerignore exists"
else
    warn ".dockerignore missing (Docker builds may be slower)"
fi

if [ -f ".gitignore" ]; then
    # Check that .env is in gitignore
    if grep -q "^\.env$" .gitignore 2>/dev/null; then
        ok ".gitignore includes .env (credentials protected)"
    else
        warn ".gitignore does not include .env — credentials may be committed!"
        info "Add '.env' to .gitignore immediately"
    fi
else
    warn ".gitignore missing — risk of committing credentials"
fi
echo ""

# ── 8. Check data directory ──────────────────────────────────
echo "── Data Directory ─────────────────────────────────"
if [ -d "data" ]; then
    ok "data/ directory exists"
    if [ -f "data/grader.db" ]; then
        DB_SIZE=$(du -h data/grader.db | cut -f1)
        info "Existing database: grader.db ($DB_SIZE)"
    else
        info "No database yet (will be created on first run)"
    fi
else
    info "data/ directory will be created on first run"
fi
echo ""

# ── 9. Check README ──────────────────────────────────────────
echo "── Documentation ────────────────────────────────────"
if [ -f "README.md" ]; then
    ok "README.md exists"
else
    warn "README.md missing"
fi
echo ""

# ── Summary ──────────────────────────────────────────────────
echo "═══════════════════════════════════════════════"
echo "  SUMMARY"
echo "═══════════════════════════════════════════════"
echo ""

if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo "  🎉  Everything looks perfect!"
    echo ""
    echo "  Run with:"
    echo "    docker compose up --build"
    echo ""
elif [ "$ERRORS" -eq 0 ]; then
    echo "  ✅  No errors, $WARNINGS warning(s)"
    echo ""
    echo "  You can run the bot, but check the warnings above."
    echo ""
    echo "  Run with:"
    echo "    docker compose up --build"
    echo ""
else
    echo "  ❌  $ERRORS error(s), $WARNINGS warning(s)"
    echo ""
    echo "  Fix the errors above before running."
    echo ""
    echo "  Quick fixes:"

    if ! [ -f ".env" ]; then
        echo "    cp .env.example .env && nano .env"
    fi

    if ! [ -d "$TOOLS_BASE" ]; then
        echo "    # Download nand2tetris from https://www.nand2tetris.org/software"
        echo "    unzip ~/Downloads/nand2tetris.zip -d /tmp/n2t"
        echo "    mkdir -p tools/nand2tetris"
        echo "    cp -r /tmp/n2t/nand2tetris/tools tools/nand2tetris/"
        echo "    chmod +x tools/nand2tetris/tools/*.sh"
    fi

    if ! [ -d "grader_test_files/project01" ]; then
        echo "    # Copy test files"
        echo "    mkdir -p grader_test_files/project01"
        echo "    cp /tmp/n2t/nand2tetris/projects/01/*.tst grader_test_files/project01/"
        echo "    cp /tmp/n2t/nand2tetris/projects/01/*.cmp grader_test_files/project01/"
    fi

    echo ""
fi

echo "═══════════════════════════════════════════════"
exit $ERRORS
