#!/bin/bash
# Test Runner for LexLink E2E Tests
#
# This script runs the E2E test suite with Gemini integration.
# Make sure the LexLink server is running before executing this script.

set -e  # Exit on error

# Colors for output
GREEN='\033[0.32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================="
echo "  LexLink E2E Test Runner"
echo "================================================="
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create .env file with LAW_OC and GOOGLE_API_KEYS"
    echo "See .env.example for template"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check if server is running
if ! curl -s http://127.0.0.1:8081 > /dev/null; then
    echo -e "${RED}Error: LexLink server is not running${NC}"
    echo ""
    echo "Please start the server first:"
    echo "  Terminal 1: uv run dev"
    echo "  Terminal 2: ./test/run_test.sh"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Server is running${NC}"

# Check if LAW_OC is set
if [ -z "$LAW_OC" ]; then
    echo -e "${RED}Error: LAW_OC not set in .env${NC}"
    exit 1
fi

echo -e "${GREEN}✓ LAW_OC configured${NC}"

# Check if Gemini API key is set
if [ -z "$GOOGLE_API_KEYS" ]; then
    echo -e "${YELLOW}⚠ GOOGLE_API_KEYS not set - Gemini tests will be skipped${NC}"
else
    echo -e "${GREEN}✓ Gemini API keys configured${NC}"
fi

echo ""
echo -e "${YELLOW}Installing test dependencies...${NC}"

# Install google-generativeai if not already installed
pip install -q google-generativeai httpx || true

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Run the test
echo -e "${YELLOW}Running E2E tests...${NC}"
echo ""

python test/test_e2e_with_gemini.py

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}================================================="
    echo -e "  All tests passed! ✓"
    echo -e "=================================================${NC}"
    echo ""
    echo "Test logs are available in: test/logs/"
    exit 0
else
    echo ""
    echo -e "${RED}================================================="
    echo -e "  Some tests failed ✗"
    echo -e "=================================================${NC}"
    echo ""
    echo "Check test logs in: test/logs/"
    exit 1
fi
