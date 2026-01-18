#!/bin/bash
# ============================================================
# check_coverage.sh - Run tests with coverage analysis
# ============================================================
#
# This script runs pytest with coverage analysis and generates
# both terminal and HTML reports. It fails if coverage is below
# the specified threshold (default: 60%).
#
# Note: FastAPI crud.py and main.py use relative imports designed
# for Docker container execution, so they show 0% coverage when
# running tests locally. The actual business logic is tested
# via mock-based tests.
#
# Usage:
#   ./check_coverage.sh           # Run with default 60% threshold
#   ./check_coverage.sh 80        # Run with 80% threshold
#   ./check_coverage.sh --html    # Generate HTML report
#
# Requirements:
#   - pytest
#   - pytest-cov
#   - pytest-asyncio
#
# ============================================================

set -e

# Configuration
COVERAGE_THRESHOLD=${1:-60}
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
COVERAGE_DIR="$PROJECT_ROOT/coverage_report"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
GENERATE_HTML=false
for arg in "$@"; do
    case $arg in
        --html)
            GENERATE_HTML=true
            shift
            ;;
        [0-9]*)
            COVERAGE_THRESHOLD=$arg
            shift
            ;;
    esac
done

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}FixMyCodeDB - Test Coverage Analysis${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Check for required packages
echo -e "${YELLOW}Checking dependencies...${NC}"
python -c "import pytest" 2>/dev/null || {
    echo -e "${RED}Error: pytest not installed. Run: pip install pytest${NC}"
    exit 1
}
python -c "import pytest_cov" 2>/dev/null || {
    echo -e "${RED}Error: pytest-cov not installed. Run: pip install pytest-cov${NC}"
    exit 1
}

echo -e "${GREEN}Dependencies OK${NC}"
echo ""

# Navigate to project root
cd "$PROJECT_ROOT"

# Build coverage arguments
# Note: fastapi_app/crud.py and fastapi_app/main.py use relative imports
# designed for Docker container execution, so we exclude them from coverage
COVERAGE_ARGS="--cov=scraper --cov=cli --cov=fastapi_app"
COVERAGE_ARGS="$COVERAGE_ARGS --cov-report=term-missing"
COVERAGE_ARGS="$COVERAGE_ARGS --cov-fail-under=$COVERAGE_THRESHOLD"

if [ "$GENERATE_HTML" = true ]; then
    COVERAGE_ARGS="$COVERAGE_ARGS --cov-report=html:$COVERAGE_DIR"
fi

# Run tests with coverage
echo -e "${YELLOW}Running tests with coverage analysis...${NC}"
echo -e "Coverage threshold: ${BLUE}${COVERAGE_THRESHOLD}%${NC}"
echo ""

# Create a temporary file to capture output
TEMP_OUTPUT=$(mktemp)

# Run pytest and capture return code
set +e
python -m pytest tests/ \
    $COVERAGE_ARGS \
    -v \
    --tb=short \
    2>&1 | tee "$TEMP_OUTPUT"
PYTEST_EXIT_CODE=${PIPESTATUS[0]}
set -e

echo ""
echo -e "${BLUE}============================================================${NC}"

# Check results
if [ $PYTEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}✓ Coverage threshold of ${COVERAGE_THRESHOLD}% met!${NC}"

    if [ "$GENERATE_HTML" = true ]; then
        echo ""
        echo -e "${GREEN}HTML coverage report generated at:${NC}"
        echo -e "  ${BLUE}$COVERAGE_DIR/index.html${NC}"
    fi
else
    echo -e "${RED}✗ Tests failed or coverage below threshold${NC}"

    # Check if it's a coverage failure
    if grep -q "FAIL Required test coverage" "$TEMP_OUTPUT" 2>/dev/null; then
        echo ""
        echo -e "${YELLOW}Coverage is below the required ${COVERAGE_THRESHOLD}%${NC}"
        echo -e "${YELLOW}Consider adding more tests to increase coverage.${NC}"
    fi
fi

# Cleanup
rm -f "$TEMP_OUTPUT"

echo -e "${BLUE}============================================================${NC}"

exit $PYTEST_EXIT_CODE
