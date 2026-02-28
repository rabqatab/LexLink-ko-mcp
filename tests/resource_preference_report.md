# MCP Resource Preference Test Report

**Date:** 2026-02-28 18:51
**Runs per model:** 50
**Query mix:** 70% cached laws / 30% uncached laws

## gemini-2.5-flash

### Overall First-Call Distribution

| Method | Count | Percentage |
|--------|------:|----------:|
| static_resource | 4 | 8.0% |
| template_resource | 46 | 92.0% |

### Cached Laws (n=35)

| Method | Count | Percentage |
|--------|------:|----------:|
| static_resource | 3 | 8.6% |
| template_resource | 32 | 91.4% |

### Uncached Laws (n=15)

| Method | Count | Percentage |
|--------|------:|----------:|
| static_resource | 1 | 6.7% |
| template_resource | 14 | 93.3% |

### Summary
- **Resource usage rate:** 50/50 (100.0%)
- **Search fallback rate:** 0/50 (0.0%)
- **Static vs Template preference:** 4 static / 46 template

---

## gemini-3-flash-preview

### Overall First-Call Distribution

| Method | Count | Percentage |
|--------|------:|----------:|
| static_resource | 15 | 30.0% |
| template_resource | 35 | 70.0% |

### Cached Laws (n=35)

| Method | Count | Percentage |
|--------|------:|----------:|
| static_resource | 13 | 37.1% |
| template_resource | 22 | 62.9% |

### Uncached Laws (n=15)

| Method | Count | Percentage |
|--------|------:|----------:|
| static_resource | 2 | 13.3% |
| template_resource | 13 | 86.7% |

### Summary
- **Resource usage rate:** 50/50 (100.0%)
- **Search fallback rate:** 0/50 (0.0%)
- **Static vs Template preference:** 15 static / 35 template

---

## Cross-Model Comparison

| Metric | gemini-2.5-flash | gemini-3-flash-preview |
|--------|--------|--------|
| Resource usage (all) | 50/50 (100%) | 50/50 (100%) |
| Resource usage (cached) | 35/50 (70%) | 35/50 (70%) |
| Search fallback (all) | 0/50 (0%) | 0/50 (0%) |
| Static resource calls | 4/50 (8%) | 15/50 (30%) |
| Template resource calls | 46/50 (92%) | 35/50 (70%) |
| Errors | 0/50 (0%) | 0/50 (0%) |
