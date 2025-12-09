# Smithery.ai Credential Handling - Approaches & Analysis

**Document Type:** Architecture Analysis
**Created:** 2025-11-07
**Status:** Active - Critical for Smithery Deployment

---

## Executive Summary

**Current Issue:** Our closure-based session config pattern does NOT work because:
1. Factory function called ONCE at startup (singleton pattern)
2. `session_config` parameter is always `None` at factory time
3. URL parameters (`?oc=value`) not passed to factory function

**Solution:** Use **context-based access** pattern recommended by Smithery.

---

## How Smithery Handles Private Keys/Credentials

### Security Model

**Session Configuration Flow:**
1. User enters credentials in Smithery UI web form
2. Smithery passes credentials as **URL query parameters** (`?oc=value&key=secret`)
3. Credentials are **ephemeral** - not stored on Smithery's servers
4. Each user session gets isolated configuration

**Security Best Practices:**
- ✅ Always serve over HTTPS (credentials in URL params)
- ✅ Never log sensitive values
- ✅ Validate input server-side even though Smithery validates too
- ✅ Configuration is session-specific (isolated per user)

### URL Parameter Format

```
http://server.com/mcp?oc=ddongle0205&debug=true&timeout=30
```

Supports dot notation for nested config:
```
http://server.com/mcp?api.key=secret&model.name=gpt-4
```

---

## Approach Comparison

### ❌ **Current Approach: Closure Pattern (BROKEN)**

```python
@smithery.server(config_schema=LexLinkConfig)
def create_server(session_config: Optional[LexLinkConfig] = None) -> FastMCP:
    """
    Problem: session_config is ALWAYS None!
    - Factory called once at startup (singleton)
    - URL params not passed to factory
    - Captured in closure but value is permanently None
    """

    def _resolve_oc(override_oc: Optional[str] = None) -> str:
        return resolve_oc(
            override_oc=override_oc,
            session_oc=session_config.oc if session_config else None  # ← ALWAYS None!
        )

    @server.tool()
    def eflaw_search(..., oc: Optional[str] = None):
        resolved_oc = _resolve_oc(oc)  # ← Broken - falls back to env var
```

**Why it fails:**
- Factory is called at module load time, before any sessions exist
- `session_config` parameter receives `None` at startup
- Closure captures `None` value permanently
- Tool calls have no access to actual session config

**Test Results:**
- ✅ Works in local dev IF `export LAW_OC=...` (Priority 3 - env var)
- ❌ Fails in Smithery production (no env var, session config is None)

---

### ✅ **Recommended Approach: Context Parameter Injection**

**VERIFIED** pattern from Smithery Python SDK docs and real-world examples:

```python
from mcp.server.fastmcp import FastMCP, Context  # ← Import Context
from smithery.decorators import smithery

@smithery.server(config_schema=LexLinkConfig)
def create_server(session_config: Optional[LexLinkConfig] = None) -> FastMCP:
    """
    Factory called once at startup - DON'T access session_config here!
    """
    server = FastMCP("LexLink - Korean Law API")

    @server.tool()
    def eflaw_search(
        query: str,
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,  # ← Add Context parameter
        # ... other params
    ) -> dict:
        """Search laws - access session config at request time via Context."""

        # Access session config from Context at REQUEST time!
        config = ctx.session_config if ctx else None  # ← ACTUAL session config!

        # Resolve OC with correct priority
        resolved_oc = resolve_oc(
            override_oc=oc,  # Priority 1: Tool argument
            session_oc=config.oc if config else None  # Priority 2: Session config (NOW WORKS!)
        )

        # ... rest of tool logic
```

**How it works:**
1. Factory called once at startup (ignore `session_config` parameter - it's None)
2. Tool function called per request
3. **FastMCP injects `ctx: Context` automatically** at request time
4. `ctx.session_config` contains **this session's configuration** from URL params
5. Config is isolated per session/user

**Benefits:**
- ✅ **Verified pattern** - used by official Smithery Python SDK
- ✅ Session config actually accessible at request time
- ✅ Each user gets isolated configuration
- ✅ Works in both local dev and Smithery production
- ✅ Supports all 3 priority levels:
  1. Tool argument override
  2. Session config (via Context)
  3. Environment variable fallback
- ✅ FastMCP handles Context injection automatically

---

### 🔧 **Alternative Approach: Tool Argument Only**

```python
@server.tool()
def eflaw_search(
    query: str,
    oc: str,  # ← REQUIRED, not Optional
    display: int = 20,
    type: str = "XML",
) -> dict:
    """
    Force users to pass OC in every call.
    Simplest but poorest UX.
    """
    # No resolution needed - just use oc directly
    params = {"oc": oc, "query": query, ...}
```

**Pros:**
- ✅ Simple implementation
- ✅ Works everywhere
- ✅ No session config complexity

**Cons:**
- ❌ Poor UX - users must pass `oc` in every call
- ❌ Violates PRD requirement FR11 (session config)
- ❌ Defeats purpose of Smithery's session config feature

---

## Real-World Examples

### Exa Search MCP (TypeScript)
**Repository:** https://github.com/exa-labs/exa-mcp-server

**Pattern:** Config passed to tools via closure
```typescript
export default function ({ config }: { config: z.infer<typeof configSchema> }) {
  const normalizedConfig = { ...config, enabledTools: parsedEnabledTools };

  // Tools receive config during registration
  if (shouldRegisterTool('web_search_exa')) {
    registerWebSearchTool(server, normalizedConfig);
  }
}

// Tool implementation
export function registerWebSearchTool(
  server: McpServer,
  config?: { exaApiKey?: string }
): void {
  // Access API key with fallback
  'x-api-key': config?.exaApiKey || process.env.EXA_API_KEY || ''
}
```

### Brave Search MCP (TypeScript)
**Repository:** https://github.com/brave/brave-search-mcp-server

**Pattern:** Config managed via state and command-line options
```typescript
// config.ts
braveApiKey: process.env.BRAVE_API_KEY ?? ''

.option('--brave-api-key <string>', 'Brave API key',
  process.env.BRAVE_API_KEY ?? '')
```

### Smithery Cookbook (Python)
**Repository:** https://github.com/smithery-ai/smithery-cookbook

**Pattern:** Middleware + global state
```python
# Global state
current_api_key: Optional[str] = None

def set_api_key(api_key: Optional[str]):
    global current_api_key
    current_api_key = api_key

# Middleware extracts config from query params
app = SmitheryConfigMiddleware(app, set_api_key)

# Tools access at request time
@mcp.tool()
def count_characters(text: str, character: str) -> str:
    if not validate_api_key(current_api_key):  # ← Access global state
        raise ValueError("API key required!...")
```

**Note:** Cookbook uses custom container with HTTP middleware. Our implementation uses Smithery Python SDK's `@smithery.server` decorator, which provides Context injection automatically.

### Official Smithery Python SDK Pattern
**Documentation:** https://smithery.ai/docs/build/session-config

**Pattern:** Context parameter injection (RECOMMENDED FOR US)
```python
from mcp.server.fastmcp import FastMCP, Context

@smithery.server(config_schema=ConfigSchema)
def create_server():
    server = FastMCP(name="My Server")

    @server.tool()
    def my_tool(query: str, ctx: Context) -> str:
        config = ctx.session_config  # ← Access at request time!
        print(f"Using model: {config.model_name}")
        return f"Response using {config.model_name}"
```

**Key insight:** Python SDK handles Context injection automatically - no middleware needed!

---

## Implementation Plan: Context Parameter Injection

### Changes Required:

#### 1. Update `src/lexlink/server.py`

**Import Context:**
```python
from mcp.server.fastmcp import FastMCP, Context  # ← Add Context import
```

**Current (broken):**
```python
def create_server(session_config: Optional[LexLinkConfig] = None):
    def _resolve_oc(override_oc: Optional[str] = None) -> str:
        return resolve_oc(
            override_oc=override_oc,
            session_oc=session_config.oc if session_config else None  # ← BROKEN
        )

    @server.tool()
    def eflaw_search(..., oc: Optional[str] = None):
        resolved_oc = _resolve_oc(oc)
```

**Fixed (Context parameter injection):**
```python
def create_server(session_config: Optional[LexLinkConfig] = None):
    server = FastMCP("LexLink - Korean Law API")

    @server.tool()
    def eflaw_search(
        query: str,
        display: int = 20,
        page: int = 1,
        oc: Optional[str] = None,
        type: str = "XML",
        ctx: Context = None,  # ← Add Context parameter
        # ... other params
    ):
        # Access session config from Context at REQUEST time
        config = ctx.session_config if ctx else None
        session_oc = config.oc if config else None

        # Resolve OC with all 3 priorities working
        resolved_oc = resolve_oc(
            override_oc=oc,           # Priority 1: Tool argument
            session_oc=session_oc     # Priority 2: Session config (NOW WORKS!)
        )
        # Priority 3: Environment variable (in resolve_oc function)
```

**Key changes:**
1. Import `Context` from `mcp.server.fastmcp`
2. Add `ctx: Context = None` parameter to tool function signature
3. Access `ctx.session_config` at REQUEST time (not factory time)
4. No try/except needed - FastMCP handles Context injection safely

#### 2. Update All Tools

Apply the same pattern to all 6 tools:
- `eflaw_search`
- `law_search`
- `eflaw_service`
- `law_service`
- `eflaw_josub`
- `law_josub`

#### 3. Update Tests

Test WITHOUT environment variable to verify session config works:
```bash
# Start server without LAW_OC
uv run dev

# Test should pass using session config from URL params
export GOOGLE_API_KEYS="..."
uv run python test/test_e2e_with_gemini.py
```

#### 4. Remove Diagnostic Logging

Clean up the factory call tracking code (lines 31-80 in server.py).

---

## Testing Strategy

### Phase 1: Local Testing with Context Access

```bash
# Terminal 1: Start server WITHOUT environment variable
uv run dev

# Terminal 2: Test with session config in URL
curl -H "Accept: application/json" \
  "http://127.0.0.1:8081/mcp?oc=ddongle0205" \
  -d '{"method":"tools/call","params":{"name":"eflaw_search","arguments":{"query":"자동차관리법","type":"XML"}}}'
```

**Expected:** Tool should use `oc` from URL parameter via context.

### Phase 2: E2E Test Without Environment Variable

```bash
# Start server without LAW_OC
uv run dev

# Run E2E tests - should pass using session config
uv run python test/test_e2e_with_gemini.py
```

**Expected:** 4/5 or 5/5 tests passing without environment variable.

### Phase 3: Smithery Production Deployment

1. Deploy to Smithery
2. Configure `oc` in Smithery UI
3. Test all tools
4. Verify session isolation (different users, different OCs)

---

## Security Considerations

### Current Implementation

**What we're storing:**
- `oc`: Law.go.kr user identifier (email local part)
- Not an API key, not a password
- Similar to a username

**Security level:** LOW sensitivity
- Public API, free to use
- OC identifies requester for logging/quota purposes
- No financial or PII data exposed

### Smithery's Security Model

**Credential Transmission:**
- ✅ HTTPS required (credentials in URL params)
- ✅ Ephemeral (not stored on Smithery servers)
- ✅ Session-isolated (each user's config separate)

**Best Practices:**
- ✅ Never log `oc` value
- ✅ Validate even though Smithery validates
- ✅ Use environment variable for local dev
- ✅ Use session config for production

**Recent Security Incident (2025):**
- Path traversal vulnerability discovered by GitGuardian
- Exposed tokens from Smithery's environment
- Fixed within 2 days (June 13-15, 2025)
- No indication of exploitation in the wild
- **Implication:** Smithery takes security seriously, responds quickly

---

## Recommended Approach

### ✅ **Use Context-Based Access (Option B)**

**Rationale:**
1. **Aligns with Smithery's design** - documented pattern for Python servers
2. **Best UX** - users configure once in UI, works for all tool calls
3. **Maintains 3-tier priority** - tool arg > session config > env var
4. **Production-ready** - designed for Smithery's architecture
5. **Fulfills PRD requirements** - FR11 (session config) and FR12 (context injection)

**Implementation effort:** LOW
- Modify 2 existing tools (10 lines each)
- Add same pattern to 4 new tools
- Update tests to verify without env var
- ~1-2 hours work

**Risk:** LOW
- Well-documented pattern
- Used by other Smithery servers
- Easy to test locally before deploying

---

## Next Steps

1. ✅ **Document approaches** (this document) - DONE
2. ⚠️ **Implement context-based access** in server.py
3. ⚠️ **Update both existing tools** (eflaw_search, law_search)
4. ⚠️ **Test without environment variable** - verify session config works
5. ⚠️ **Update diagnostic document** with findings
6. ⚠️ **Remove diagnostic logging** from server.py
7. ⚠️ **Deploy to Smithery** and verify production behavior
8. ⚠️ **Update README** with correct usage patterns

---

## References

- **Smithery Session Config Docs:** https://smithery.ai/docs/build/session-config
- **FastMCP Context:** https://gofastmcp.com/servers/context
- **Smithery Python SDK:** https://pypi.org/project/smithery/
- **Security Best Practices:** https://smithery.ai/blog/mcp-auth
- **Our Diagnostic:** `docs/06_test_failure_diagnosis_20251107_trial01.md`
- **API Provider Issues:** `docs/07_api_provider_issues.md`

---

**Status:** Ready for implementation
**Priority:** HIGH - Blocks Smithery deployment
**Estimated Time:** 1-2 hours
