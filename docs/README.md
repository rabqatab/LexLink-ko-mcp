# LexLink Documentation

**Quick Navigation:**

## 📖 Core Documentation

| File | Description |
|------|-------------|
| **API_REFERENCE.md** | Complete API specifications for all 24 implemented MCP tools |
| **STATUS.md** | Current project status, implementation summary, and API coverage |
| **HISTORY.md** | Detailed implementation timeline (Phases 1-14) |

## 🗺️ Planning & Future Work

| File | Description |
|------|-------------|
| **ROADMAP.md** | Future API implementation plans and priorities |
| **API_CATALOG.md** | Complete catalog of 150+ available law.go.kr APIs |
| **ISSUES.md** | Known bugs and issues |

## 🔗 Article Citation System (Phase 4 - NEW!)

| File | Description |
|------|-------------|
| **ARTICLE_CITATION_DESIGN.md** | Technical design for citation extraction |
| **ARTICLE_CITATION_EVALUATION.md** | Testing and validation methodology |
| **SMITHERY_CITATION_CONFIG.md** | Smithery deployment configuration |

## 🔧 Technical Reference

| Directory | Description |
|-----------|-------------|
| **reference/** | Technical design documents, PRDs, implementation notes |

---

## Quick Stats

- **Total APIs Available:** 150+
- **APIs Implemented:** 24 (16%)
- **Phase 1:** 6 tools (Core laws)
- **Phase 2:** 9 tools (Extended APIs)
- **Phase 3:** 8 tools (Case law & legal research)
- **Phase 4:** 1 tool (Article citation extraction)
- **MCP Prompts:** 5 (including citation workflows)
- **Semantic Validation:** 100%
- **Version:** v1.2.0

---

## Document Purpose

### API_REFERENCE.md
Complete technical specifications for all 24 implemented APIs. Includes:
- Request parameters (snake_case format)
- Sample URLs
- Response schemas
- Phase 1: Current laws (effective/announcement date)
- Phase 2: English laws, administrative rules, law-ordinance linkage
- Phase 3: Court precedents, Constitutional Court decisions, legal interpretations, administrative appeals
- Phase 4: Article citation extraction (HTML-based, 100% accuracy)

### STATUS.md
Current project state and metrics:
- What's working (all 24 tools)
- Test results (100% passing)
- Key technical decisions
- API coverage analysis
- Production readiness status

### HISTORY.md
How we got here - complete implementation timeline:
- Phase 1-14 development history
- Technical milestones
- Architecture evolution
- Problem-solving approaches

### ROADMAP.md
Where we're going:
- Phase 4 complete (citation extraction)
- Phase 5+ plans
- Priority API additions
- Feature enhancements
- Deployment strategies

### API_CATALOG.md
The big picture - all 150+ available APIs:
- Laws (연혁, 이력, 부가서비스)
- Local ordinances (자치법규)
- Committee decisions (12 committees)
- Treaties (조약)
- Mobile APIs
- Knowledge base APIs

### ISSUES.md
Known limitations and bugs:
- JSON format not supported by API provider
- Validator limitations
- Workarounds and solutions

### ARTICLE_CITATION_DESIGN.md
Technical design for the citation extraction system:
- Architecture and data flow
- HTML parsing approach (100% accuracy)
- Component specifications
- Implementation plan

### ARTICLE_CITATION_EVALUATION.md
Testing and validation methodology:
- Unit tests for citation parsing
- Integration tests with law.go.kr
- Performance benchmarks
- Accuracy validation

### SMITHERY_CITATION_CONFIG.md
Smithery.ai deployment configuration:
- MCP prompt configuration
- System prompt templates
- Auto-citation enforcement
- Best practices

---

**See also:** `reference/` directory for technical design documents and implementation notes.
