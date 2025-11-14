# LexLink Test Suite

Comprehensive testing for the LexLink MCP server.

## Directory Structure

```
test/
├── README.md                      # This file
├── run_test.sh                    # Test runner script
│
├── Test Files:
│   ├── test_e2e_with_gemini.py    # E2E tests (5 tests)
│   ├── test_all_15_tools.py       # Comprehensive tool tests (15 tests)
│   ├── test_llm_integration.py    # LLM function calling tests (15 tests)
│   └── test_semantic_validation.py # Semantic data validation (15 tests)
│
├── docs/                          # Test documentation
│   ├── COMPREHENSIVE_TEST_SUMMARY.md
│   ├── SEMANTIC_VALIDATION_SUMMARY.md
│   └── VALIDATOR_INVESTIGATION_REPORT.md
│
├── utils/                         # Test utilities
│   ├── mcp_client.py              # MCP protocol client
│   ├── logger.py                  # Structured test logger
│   └── test_llm_remaining.py      # Helper for partial test runs
│
└── logs/                          # Test execution logs (JSON + Markdown)
```

## Test Suites

### 1. E2E Tests (`test_e2e_with_gemini.py`)

End-to-end validation of MCP protocol and basic functionality.

**Tests:**
- Server initialization
- Tool listing
- Direct tool calls
- Gemini LLM integration (optional)
- Error handling

**Run:**
```bash
python test/test_e2e_with_gemini.py
```

### 2. All Tools Test (`test_all_15_tools.py`)

Comprehensive functional testing of all 15 LexLink tools.

**Tests:**
- All 15 tools with sample queries
- Response format validation
- API connectivity
- Error handling

**Run:**
```bash
python test/test_all_15_tools.py
```

### 3. LLM Integration Tests (`test_llm_integration.py`)

Validates Gemini function calling with all 15 tools.

**Tests:**
- Function call selection
- Parameter extraction
- Tool execution
- Response synthesis
- All 15 tools tested with natural language queries

**Run:**
```bash
python test/test_llm_integration.py
```

**Status:** ✅ 15/15 tests passing (100%)

### 4. Semantic Validation (`test_semantic_validation.py`)

Validates that API responses contain meaningful Korean law data.

**Tests:**
- XML structure validation
- Korean keyword presence
- Data completeness
- All 15 tools validated

**Run:**
```bash
python test/test_semantic_validation.py
```

**Status:** ✅ 15/15 tools returning valid data (100%)

## Prerequisites

1. **Running LexLink Server**
   ```bash
   # Terminal 1: Start server
   uv run dev
   ```

2. **Environment Configuration**
   ```bash
   # Required in .env
   LAW_OC=your_id_here

   # Optional for LLM tests
   GOOGLE_API_KEYS=key1,key2,key3
   ```

3. **Test Dependencies**
   ```bash
   pip install google-generativeai httpx
   ```

## Running Tests

### Quick Start - All Tests

```bash
# Make sure server is running
uv run dev

# Run E2E tests
./test/run_test.sh
```

### Individual Test Suites

```bash
# E2E tests
python test/test_e2e_with_gemini.py

# All 15 tools
python test/test_all_15_tools.py

# LLM integration
python test/test_llm_integration.py

# Semantic validation
python test/test_semantic_validation.py
```

## Test Status

| Test Suite | Tools | Status | Coverage |
|------------|-------|--------|----------|
| E2E Tests | 2 | ✅ PASS | 5/5 (100%) |
| All Tools | 15 | ✅ PASS | 15/15 (100%) |
| LLM Integration | 15 | ✅ PASS | 15/15 (100%) |
| Semantic Validation | 15 | ✅ PASS | 15/15 (100%) |

## Test Logs

Logs are automatically saved in `test/logs/`:

- **JSON Format** (`lexlink_*_YYYYMMDD_HHMMSS.json`)
  - Machine-readable
  - Complete test data
  - All MCP calls and responses

- **Markdown Format** (`lexlink_*_YYYYMMDD_HHMMSS.md`)
  - Human-readable report
  - Formatted test results
  - Easy to share

### Log Retention

- Keeps 3 most recent test runs per test suite
- Older logs automatically cleaned up
- Total: ~20-30 log files maintained

## Configuration

### Session Config (Smithery Compatible)

```python
session_config = {
    "oc": "your_id",              # From LAW_OC env var
    "debug": False,                # Optional
    "base_url": "http://www.law.go.kr",  # Optional
    "http_timeout_s": 15           # Optional
}
```

### LLM Integration Config

```python
# Model preference order
model_preferences = [
    'gemini-1.5-flash',      # Preferred (stable, good quota)
    'gemini-1.5-pro',        # Alternative (better accuracy)
    'gemini-2.0-flash-exp',  # Experimental (latest features)
    'gemini-pro'             # Legacy fallback
]
```

## Troubleshooting

### Server Not Running
```
Error: Cannot connect to http://127.0.0.1:8081

Solution: Start server in another terminal
  uv run dev
```

### Missing LAW_OC
```
Error: LAW_OC environment variable not set

Solution: Add to .env file
  LAW_OC=your_id_here
```

### Gemini Rate Limits
```
Error: 429 ResourceExhausted

Solution 1: Wait 60 seconds for quota reset
Solution 2: Use multiple API keys (comma-separated in .env)
Solution 3: Run tests with delays using test_llm_remaining.py helper
```

### Import Errors
```
ImportError: No module named 'google.generativeai'

Solution: Install dependencies
  pip install google-generativeai httpx
```

## CI/CD Integration

```bash
# Start server in background
uv run dev &
SERVER_PID=$!

# Wait for server to be ready
sleep 5

# Run all test suites
python test/test_e2e_with_gemini.py
python test/test_all_15_tools.py
python test/test_llm_integration.py
python test/test_semantic_validation.py

# Cleanup
kill $SERVER_PID
```

## Test Documentation

See `test/docs/` for detailed test reports:

- **COMPREHENSIVE_TEST_SUMMARY.md** - Overall test status and results
- **SEMANTIC_VALIDATION_SUMMARY.md** - Data quality validation details
- **VALIDATOR_INVESTIGATION_REPORT.md** - 100% validation achievement journey

## Related Documentation

- Main README: `../README.md`
- Project Status: `../docs/DEVELOPMENT.md`
- API Specification: `../docs/API_SPEC.md`
- Implementation History: `../docs/DEVELOPMENT_HISTORY.md`
