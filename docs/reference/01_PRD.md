# LexLink MCP Server - Product Requirements Document

**Version:** 1.0
**Last Updated:** 2025-11-06
**Status:** Draft
**Owner:** Development Team

---

## 1. Executive Summary

LexLink is an MCP (Model Context Protocol) server that exposes the Korean National Law Information API to AI agents and LLM applications. By providing standardized tool definitions for 6 law information endpoints, LexLink enables AI systems to reliably search, retrieve, and analyze Korean legal information without requiring developers to handle complex API integration, parameter encoding, or authentication logic.

**Key Value Proposition:** Reduce AI legal research integration from weeks to hours through standardized, agent-friendly API access.

---

## 2. Background & Problem Statement

### Current State
- The Korean National Law Information API (law.go.kr) provides comprehensive access to current laws, regulations, and legal provisions
- The API requires specific parameter formats (e.g., OC user identifier, 6-digit article codes) and supports multiple response formats (HTML/XML/JSON)
- AI developers building legal research tools must manually integrate these APIs, handling authentication, parameter encoding, and response parsing

### Problems
1. **Integration Complexity:** Developers spend 2-4 weeks learning API quirks (parameter naming, encoding requirements, response formats)
2. **Inconsistent Access:** Direct API calls from AI agents often fail due to missing required parameters (especially OC identifier)
3. **Poor Error Visibility:** Generic 403/500 errors provide no guidance on what went wrong
4. **Limited Reusability:** Each project rebuilds the same API wrapper logic

### Opportunity
Smithery's MCP platform enables standardized tool exposure for AI agents. By wrapping the law.go.kr API as MCP tools, we can provide a battle-tested integration that works out-of-the-box with Claude, GPT, and other MCP-compatible agents.

---

## 3. Target Users & Stakeholders

### Primary Users
1. **AI/LLM Application Developers**
   - Building legal research assistants, compliance checkers, or regulatory analysis tools
   - Need reliable access to Korean law data for RAG (Retrieval-Augmented Generation)
   - Prefer standardized interfaces over custom API clients

2. **Legal Tech Companies**
   - Creating automated contract review, compliance monitoring, or legal Q&A systems
   - Require high availability and clear error messaging
   - Need to integrate multiple legal data sources

3. **AI Agents/LLMs**
   - Claude, GPT-4, and other models using MCP tools
   - Need structured, predictable tool interfaces
   - Benefit from consistent error handling

### Stakeholders
- **Government (law.go.kr maintainers):** Interested in increased API adoption and proper usage patterns
- **Smithery Platform:** Benefits from showcasing a real-world government API integration
- **Open Source Community:** Potential contributors and users of Korean legal tech tools

---

## 4. Business Goals & Success Metrics

### Business Goals
1. **Accelerate Integration:** Reduce time-to-first-successful-call from 2 weeks → 1 hour
2. **Improve Reliability:** Achieve 95%+ API call success rate (vs. ~60% with naive integrations)
3. **Enable Adoption:** Onboard 10+ projects using LexLink within 3 months
4. **Establish Best Practices:** Become reference implementation for MCP government API wrappers

### Success Metrics
| Metric | Target | Measurement |
|--------|--------|-------------|
| API Call Success Rate | ≥ 95% | Successful responses / Total calls |
| Time to First Success | ≤ 1 hour | Developer onboarding time (setup → first valid response) |
| Error Message Clarity | ≥ 90% resolution without support | Survey: "Could you resolve errors independently?" |
| Response Time | ≤ 2 seconds | P95 latency for search queries |
| Documentation Completeness | 100% endpoints covered | All 6 tools have examples + error scenarios |

---

## 5. User Stories

### Core Workflows
1. **As an AI agent**, I want to search for laws by keyword (e.g., "자동차관리법") so that I can answer user questions about specific regulations
   - Acceptance: Returns list of matching laws with titles, IDs, effective dates

2. **As an AI agent**, I want to retrieve full text of a specific law so that I can analyze its provisions and cite specific articles
   - Acceptance: Returns complete law content including articles, paragraphs, items, and sub-items

3. **As an AI agent**, I want to query specific articles/paragraphs (조·항·호·목) so that I can provide precise legal citations without retrieving entire documents
   - Acceptance: Returns only requested article/paragraph/item content

4. **As a developer**, I want clear error messages when required parameters are missing so that I can quickly fix integration issues
   - Acceptance: Error includes missing parameter name, resolution steps, and priority order (tool arg > session config > env var)

5. **As a developer**, I want to configure authentication once (session config) so that I don't need to pass OC identifier with every tool call
   - Acceptance: Session config persists across tool calls within same session

6. **As a developer**, I want to choose response formats (JSON/XML/HTML) so that I can optimize for my downstream processing needs
   - Acceptance: All tools support type parameter with consistent format handling

### Edge Cases
7. **As an AI agent**, I want graceful handling of upstream API timeouts so that my conversation flow doesn't hang indefinitely
   - Acceptance: Returns friendly error after 15s, suggests retry or narrower query

8. **As a developer**, I want to test tools in Smithery Playground so that I can validate integration before deploying
   - Acceptance: All 6 tools callable from Playground with example arguments

---

## 6. Functional Requirements

### Must Have (P0)
- **FR1:** Expose 6 MCP tools mapping to law.go.kr API endpoints:
  1. `eflaw_search` - Search laws by effective date
  2. `eflaw_service` - Retrieve law content by effective date
  3. `law_search` - Search laws by announcement date
  4. `law_service` - Retrieve law content by announcement date
  5. `eflaw_josub` - Query specific articles/paragraphs (effective date)
  6. `law_josub` - Query specific articles/paragraphs (announcement date)

- **FR2:** Support OC (user identifier) parameter through multiple sources:
  - Tool argument (highest priority)
  - Session configuration (medium priority)
  - Environment variable LAW_OC (fallback)
  - Clear error if none provided

- **FR3:** Support response type selection (HTML, XML, JSON) for all tools
  - Default: XML (API default)
  - JSON responses normalized with consistent field names

- **FR4:** Handle Korean character encoding (UTF-8) correctly, especially for `mok` (목) parameter

- **FR5:** Provide actionable error messages including:
  - Error type (MISSING_OC, UPSTREAM_ERROR, TIMEOUT, VALIDATION_ERROR)
  - Resolution hints specific to the error
  - Request ID for debugging

- **FR11:** Server factory accepts session configuration and wires it to tools
  - `create_server(session_config: Optional[ConfigSchema] = None) -> FastMCP` signature is required
  - Session config must be reachable by tools via `ctx: Context` or closure pattern

- **FR12:** Tool context injection and signature hygiene
  - Tools either (a) declare `ctx: Context` with no default, or (b) use closure-captured session config (no `ctx`)
  - Unit tests verify `ctx` injection works and session config is accessible

### Should Have (P1)
- **FR6:** Normalize parameter names from snake_case (tool interface) to original API format (efYd, ancNo, JO, HANG, HO, MOK)
  - Reference: `docs/03_api_spec.md` for complete mapping

- **FR7:** Log key request metadata (without exposing PII):
  - Request method, path, session ID
  - OC presence indicator (true/false, not actual value)
  - Response status code, latency
  - Error types

- **FR8:** Support common search parameters:
  - Pagination (display, page)
  - Sorting (sort parameter)
  - Date ranges (ef_yd, anc_yd)
  - Ministry filtering (org)
  - Law type filtering (knd)

- **FR9:** Handle partial law retrieval:
  - Specific article codes (JO: 6-digit format like 000300)
  - Paragraph/item/sub-item filtering

### Could Have (P2)
- **FR10:** Response caching for identical queries (15-minute TTL)
- **FR11:** Retry logic with exponential backoff for transient failures
- **FR12:** Request/response size limits to prevent memory issues
- **FR13:** Rate limiting awareness with friendly error messages

### Won't Have (Out of Scope)
- Bulk data download or crawling capabilities
- Asynchronous/batch processing pipelines
- Advanced caching strategies (Redis, distributed cache)
- Historical law version comparison features
- Legal text analysis or NLP processing
- User account management or usage tracking
- Commercial API key management (only public API access)

---

## 7. Non-Functional Requirements

### Performance
- **NFR1:** API calls complete within 5 seconds (P95) for typical search queries (observed upstream latency varies 1–5s)
- **NFR2:** Tool initialization completes within 500ms

### Reliability
- **NFR3:** 95% API call success rate under normal conditions
- **NFR4:** Graceful degradation when upstream API is slow/unavailable

### Usability
- **NFR5:** Error messages understandable by developers without MCP/law.go.kr expertise
- **NFR6:** Tool descriptions in English, with Korean terms in parentheses
- **NFR7:** Example queries provided for each tool in documentation

### Security
- **NFR8:** No logging of sensitive configuration values (OC, full query strings)
- **NFR9:** Input validation to prevent injection attacks
- **NFR10:** Prefer HTTPS for upstream API calls; fallback to HTTP only if upstream lacks HTTPS, and document transport mode

### Maintainability
- **NFR11:** Session configuration schema documented with field descriptions
- **NFR12:** Parameter mapping rules centralized and testable
- **NFR13:** Clear separation between MCP layer and API client logic

---

## 8. Dependencies & Constraints

### Technical Dependencies
- **FastMCP framework** - MCP server implementation
- **Smithery platform** - Deployment and session management
- **law.go.kr API** - Upstream data source (public, no SLA)

### Known Constraints
1. **Upstream API Limitations:**
   - Rate limits unknown (not documented publicly)
   - Response times can vary (1-5 seconds observed)
   - No webhook/streaming support

2. **MCP Protocol Constraints:**
   - Session configuration must use specific naming (avoid reserved words: api_key, profile, config)
   - Context injection requires exact type hints
   - Tool arguments must be JSON-serializable

3. **Past Issues to Prevent:**
   - OC parameter was previously not passed to upstream API (case sensitivity mismatch)
   - Session config not reaching tool functions (factory function signature issue)

### External Dependencies
- Internet connectivity to law.go.kr
- Smithery platform availability
- Python 3.10+ runtime environment

---

## 9. Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OC parameter still not passed correctly | High | Medium | Comprehensive E2E test covering all parameter sources; request logging with OC presence indicator |
| Upstream API changes format | High | Low | Version responses; automated integration tests; monitor for breaking changes |
| Upstream API has undocumented rate limits | Medium | Medium | Implement client-side rate limiting; log 429 responses; provide clear user guidance |
| Korean encoding issues | Medium | Medium | Unit tests for all Korean character types; UTF-8 validation at boundaries |
| Session config not injected by Smithery | High | Low | Follow Smithery best practices; test in Playground before release |
| Unclear error messages confuse users | Medium | Medium | User testing of error scenarios; maintain error message guidelines |

---

## 10. Acceptance Criteria (Definition of Done)

### Minimum Viable Product (MVP)
- [ ] All 6 tools callable from Smithery Playground with example arguments
- [ ] OC parameter successfully passed through all three sources (tool arg, session, env)
- [ ] At least one successful end-to-end call per tool documented with screenshots
- [ ] Error handling returns structured error objects with resolution hints
- [ ] Korean characters (특히 "목" parameter) correctly encoded
- [ ] Documentation includes quick start guide with curl examples
- [ ] API specification document (`03_api_spec.md`) matches implementation

### Quality Gates
- [ ] 95%+ success rate in E2E test suite (minimum 10 scenarios)
- [ ] All error conditions covered with specific test cases
- [ ] No PII/sensitive data in logs (verified by log inspection)
- [ ] Tool descriptions clear enough for AI agents to select correct tool
- [ ] Response schemas consistent across JSON/XML/HTML formats (where applicable)

### Launch Readiness
- [ ] Published to Smithery marketplace with proper metadata
- [ ] README with installation instructions and usage examples
- [ ] At least one external user successfully integrated (pilot testing)
- [ ] Monitoring/logging provides visibility into common errors
- [ ] Known issues documented with workarounds

---

## 11. Future Considerations (Post-MVP)

### Phase 2 Enhancements
- Advanced search features (fuzzy matching, synonym expansion)
- Caching layer for frequently accessed laws
- Webhook support for law update notifications (if upstream adds support)
- Multi-language support for tool descriptions (Korean, English)

### Integration Opportunities
- Integration with other Korean government APIs (precedent search, administrative rules)
- Export to legal citation formats (Bluebook, etc.)
- Integration with legal knowledge graphs

### Platform Evolution
- Support for MCP protocol updates
- Migration to async/streaming responses if MCP supports it
- Performance optimization based on production usage patterns

---

## 12. References

- **API Specification:** `docs/03_api_spec.md` - Complete endpoint documentation with parameter mappings
- **Smithery MCP Documentation:** [Smithery Guide] - Session config, tool definition patterns
- **Law.go.kr API:** http://www.law.go.kr - Official government legal information portal
- **MCP Protocol:** [Model Context Protocol Specification]

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **OC** | User identifier derived from email local part (e.g., g4c@korea.kr → g4c). Required by law.go.kr API for all requests. |
| **eflaw** | Effective date law - law information organized by enforcement date |
| **law** | Announcement date law - law information organized by publication date |
| **조 (JO)** | Article - main subdivision of a law (6-digit code: 000300 = Article 3) |
| **항 (HANG)** | Paragraph - subdivision of an article |
| **호 (HO)** | Item - numbered point within a paragraph |
| **목 (MOK)** | Sub-item - lettered point within an item (가, 나, 다...) |
| **MST** | Law sequence identifier (alternative to ID for lookups) |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-06 | Dev Team | Initial PRD - separated from technical design document |

---

**Approval Required From:**
- [ ] Product Owner
- [ ] Technical Lead
- [ ] QA Lead
