# AGENTS.md - AI Agent Guidelines & CAVEMAN Development Manifesto

**Version:** 1.0  
**Date:** 2026-08-17  
**Purpose:** Define how AI agents and developers must operate on the Document Processing Pipeline project

---

## Preamble: The CAVEMAN Manifesto

This project adheres to the **CAVEMAN Manifesto** — a development philosophy emphasizing pragmatism, clarity, and incremental value delivery. All decisions, code changes, and feature implementations MUST respect these core principles:

### 🟢 **C** — Clarity
- Code is read far more often than written
- Variable names must be unambiguous and descriptive
- Complex logic requires clear comments explaining the "why," not the "what"
- Document design decisions; future maintainers matter
- No clever tricks; prefer boring, obvious code

### 🟢 **A** — Avoid Over-Engineering
- Build what is needed NOW, not what might be needed later
- One-size-fits-all abstractions are the enemy
- If you're not sure if you need it, you probably don't
- YAGNI (You Aren't Gonna Need It) is a feature, not a bug
- Premature generalization causes more problems than it solves

### 🟢 **V** — Value
- Every line of code must contribute to measurable user value
- Shipping 80% working beats shipping 100% perfect (iteratively)
- Collect feedback early; adjust based on real usage, not assumptions
- Batch improvements; small incremental releases beat big rewrites
- Cost-benefit analysis is mandatory for major features

### 🟢 **E** — Eagerness
- Get working code deployed quickly (within days, not months)
- Fail fast and iterate; incomplete features are better than blockers
- Celebrate shipping; perfectionism is the enemy of progress
- Monitor production continuously; live data beats staged testing
- Retrospectives drive continuous improvement

### 🟢 **M** — Minimize
- Minimize dependencies; every library is a liability
- Minimize complexity; simpler code is easier to debug, maintain, maintain, and extend
- Minimize API surface; smaller interfaces are easier to understand
- Minimize configuration; sensible defaults > config files
- Minimize CPU/memory/bandwidth; efficiency matters on constrained hardware (NAS)

### 🟢 **A** — Agility
- Adapt to user feedback without lengthy planning cycles
- Be prepared to pivot; avoid sunk-cost fallacies
- Embrace uncertainty; iterative design discovers better solutions
- Refactor fearlessly (because tests catch regressions)
- Communicate changes transparently; silence breeds fear

### 🟢 **N** — Nudge
- Improve one thing at a time; compound effects matter
- Favor small PRs over large refactors (easier review, faster merge)
- Suggest, don't dictate; involve the team in decisions
- Measure before optimizing; premature tuning wastes time
- User experience improvements are valuable, even if small

### 🟢 **M** — Mindfulness
- Be aware of trade-offs; nothing is free
- Performance vs. readability: document the choice
- Cost vs. convenience: what matters for THIS project?
- Scope vs. timeline: make trade-offs explicit
- Innovation vs. stability: know which is appropriate for this phase

---

## 1. Agent Constraints & Behavioral Rules

### 1.1 Required Compliance

All AI agents working on this project **MUST**:

1. ✅ **Read all three specification documents first** before proposing changes:
   - `docs/specs/SYSTEM_SPECIFICATION.md` (architecture & design)
   - `docs/guides/WORKFLOW_TESTING_DEBUGGING.md` (quality standards)
   - `docs/guides/DEPLOYMENT_MANAGEMENT_MANUAL.md` (operational constraints)

2. ✅ **Respect the CAVEMAN principles** in every decision:
   - Prefer simple over clever
   - Minimize dependencies
   - Deliver value incrementally
   - Avoid speculative features

3. ✅ **Validate against specifications** before implementing:
   - Does this align with the system architecture?
   - Are there existing tools/patterns to reuse?
   - Will this increase testing burden?
   - Is this minimal or over-engineered?

4. ✅ **Test requirements are non-negotiable**:
   - Unit tests for new functionality (85%+ coverage)
   - Integration tests for API changes
   - Regression tests for bug fixes
   - Property-based tests for validation logic

5. ✅ **Document changes immediately**:
   - Inline code comments for complex logic
   - Update relevant docs if architecture changes
   - Maintain CHANGELOG.md with all modifications
   - Explain the "why," not just the "what"

6. ✅ **Seek feedback before major work**:
   - Propose design via GitHub issue first
   - Wait for approval before implementation
   - Discuss trade-offs explicitly
   - Involve stakeholders early

### 1.2 Prohibited Actions

AI agents **MUST NOT**:

- ❌ Add dependencies without explicit justification & approval
- ❌ Introduce new configuration options beyond those in `.env`
- ❌ Skip or minimize testing ("we'll test it later" never happens)
- ❌ Over-generalize code ("this might be useful for X in the future")
- ❌ Commit directly to `main` branch; all changes via PR
- ❌ Ignore warnings from linters, type checkers, or security scanners
- ❌ Change behavior without updating corresponding tests
- ❌ Introduce breaking API changes without deprecation period
- ❌ Modify deployment procedures without updating this document
- ❌ Proceed with uncertainty; clarify requirements first

### 1.3 Decision-Making Flowchart

```
┌─ Feature Request / Bug Report ──────────────────┐
│                                                 │
├─ Does it align with SYSTEM_SPECIFICATION.md?  │
│  NO  → Clarify scope; propose addendum         │
│  YES → Continue                                │
│                                                 │
├─ Is implementation clear & minimal?            │
│  NO  → Simplify design; reduce scope           │
│  YES → Continue                                │
│                                                 │
├─ Will this require new dependencies?           │
│  YES → Justify in design doc; seek approval    │
│  NO  → Continue                                │
│                                                 │
├─ Can we deliver 80% in <1 day of work?         │
│  NO  → Break into smaller tasks                │
│  YES → Continue                                │
│                                                 │
├─ Is testing strategy clear?                    │
│  NO  → Plan tests before coding                │
│  YES → Implement with tests                    │
│                                                 │
└─ PROCEED WITH IMPLEMENTATION ──────────────────┘
```

---

## 2. Task Execution Guidelines

### 2.1 Before Starting Any Task

**Checklist:**

1. [ ] Read this AGENTS.md fully
2. [ ] Review relevant spec section(s)
3. [ ] Check for existing implementation (don't duplicate)
4. [ ] Identify dependencies (external APIs, libraries, other modules)
5. [ ] Draft minimal test cases
6. [ ] Estimate effort (if >1 day, break into smaller tasks)
7. [ ] Seek approval if scope is unclear

### 2.2 During Implementation

**Workflow:**

```
1. Create feature branch: git checkout -b feature/short-description
2. Write failing tests FIRST (TDD approach)
3. Implement minimum viable solution
4. Run linters, type checkers, security scanners
5. Get all tests passing (unit + integration)
6. Write/update inline documentation
7. Create PR with clear description referencing spec
8. Address review feedback iteratively
9. Merge when approved & all CI checks pass
10. Update CHANGELOG.md and relevant docs
```

### 2.3 Code Review Criteria

**PRs are approved ONLY IF:**

- ✅ All tests pass (unit, integration, fuzzing)
- ✅ Code coverage doesn't decrease
- ✅ No new linter warnings
- ✅ Type checking passes (mypy)
- ✅ Security scan passes (bandit)
- ✅ Follows project style guide
- ✅ Documentation updated (inline + external docs)
- ✅ Commit messages are clear & referential
- ✅ Changes align with CAVEMAN principles
- ✅ Performance impact documented (if any)

---

## 3. Scope Boundaries

### 3.1 What IS in Scope

✅ Bug fixes (regression tests required)  
✅ Performance optimizations with measured benefits  
✅ API improvements with backward compatibility  
✅ Documentation clarifications & examples  
✅ Dependency updates (security patches)  
✅ Test coverage improvements  
✅ Logging/monitoring enhancements  
✅ Error handling improvements  

### 3.2 What Requires Approval First

🟡 New external API integrations  
🟡 Database schema changes  
🟡 New configuration options  
🟡 Architecture changes  
🟡 Removal of features  
🟡 Breaking API changes  
🟡 New major dependencies  

### 3.3 What IS Out of Scope

❌ Features not mentioned in specifications  
❌ UI redesigns without stakeholder input  
❌ Deployment to infrastructure outside Synology  
❌ Compliance with standards not required by business  
❌ Optimization for use cases not in business plan  
❌ Support for document types beyond PDF  

---

## 4. Specific Technology & Implementation Guidelines

### 4.1 Backend (Python/FastAPI)

**DO:**
- ✅ Use type hints on all functions (PEP 484)
- ✅ Validate input via Pydantic models
- ✅ Use `async`/`await` for I/O-bound operations
- ✅ Return appropriate HTTP status codes (400, 403, 404, 500, etc.)
- ✅ Log with structured JSON (use logging module, not print)
- ✅ Cache AI API responses where appropriate
- ✅ Use environment variables for all configuration

**DON'T:**
- ❌ Use global variables (except config)
- ❌ Hardcode API keys or credentials
- ❌ Suppress exceptions without logging
- ❌ Assume file existence; validate paths
- ❌ Mix business logic with HTTP handling
- ❌ Make external API calls from background jobs without timeouts/retries

**Example Pattern:**

```python
# ✅ GOOD: Clear, testable, type-hinted
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
import logging

router = APIRouter(prefix="/api", tags=["documents"])
logger = logging.getLogger(__name__)

class DocumentMetadata(BaseModel):
    doc_id: str
    page_count: int

@router.get("/document/{doc_id}", response_model=DocumentMetadata)
async def get_document(doc_id: str):
    """Retrieve document metadata.
    
    Args:
        doc_id: Unique document identifier (UUID format)
        
    Returns:
        DocumentMetadata with page count
        
    Raises:
        HTTPException(404): Document not found
    """
    try:
        metadata = await storage.get_metadata(doc_id)
        if not metadata:
            logger.warning(f"Document not found", extra={"doc_id": doc_id})
            raise HTTPException(status_code=404, detail="Document not found")
        return metadata
    except Exception as e:
        logger.error(f"Error retrieving document", extra={"doc_id": doc_id, "error": str(e)})
        raise HTTPException(status_code=500, detail="Internal server error")
```

### 4.2 Frontend (React/Next.js)

**DO:**
- ✅ Separate concerns: components, hooks, utilities
- ✅ Use TypeScript; no untyped `any`
- ✅ Handle API errors gracefully (show user feedback)
- ✅ Test user interactions (not implementation details)
- ✅ Lazy load large components
- ✅ Display loading/error states for async operations
- ✅ Use accessible HTML (`aria-*` attributes)

**DON'T:**
- ❌ Store sensitive data in localStorage
- ❌ Make API calls in useEffect without cleanup
- ❌ Deeply nest components (extract to separate files)
- ❌ Mix styling approaches (stick to Tailwind)
- ❌ Ignore CORS errors; debug root cause
- ❌ Render without error boundaries

### 4.3 Testing

**DO:**
- ✅ Write tests BEFORE code (TDD)
- ✅ Test behavior, not implementation
- ✅ Use descriptive test names (`test_split_at_page_15_includes_page_15`)
- ✅ Mock external dependencies (AI APIs, storage)
- ✅ Use fixtures for common setup
- ✅ Test edge cases & error paths
- ✅ Run full test suite before committing

**DON'T:**
- ❌ Skip testing because "it's obvious"
- ❌ Test implementation details (private methods)
- ❌ Rely on test order; each test is independent
- ❌ Use sleep() to wait for results (use explicit waits)
- ❌ Leave TODO comments in tests

### 4.4 Dependencies

**Before adding ANY external package:**

1. Justify its necessity in the PR description
2. Check for security vulnerabilities (`safety check`)
3. Verify compatibility with Python 3.9+
4. Confirm it doesn't duplicate existing functionality
5. Document why this is better than building it

**Approved minimal dependencies:**

```
# Backend
FastAPI              # Web framework (lightweight)
PyMuPDF              # PDF manipulation (no alternative)
pydantic             # Data validation (FastAPI standard)
python-multipart     # File uploads (FastAPI requirement)
httpx                # HTTP client (async)
pytesseract          # OCR (optional, lightweight wrapper)

# Testing
pytest               # Test runner (industry standard)
pytest-asyncio       # Async test support
hypothesis           # Property-based testing
pytest-cov           # Coverage reporting
pytest-mock          # Mocking (pytest plugin)

# Quality
mypy                 # Type checking
flake8               # Linting
bandit               # Security scanning
black                # Code formatting (opinionated, saves debate)

# Frontend
react                # UI library
next.js              # React framework
typescript           # Type safety
tailwindcss          # Styling (utility-first)
```

**Never add without explicit approval:**
- ORM libraries (use raw queries or query builder)
- Full-stack frameworks (use FastAPI + React separately)
- ML frameworks (use cloud APIs instead)
- Messaging queues (simple task queue first)

---

## 5. Performance & Resource Constraints

### 5.1 Performance Targets (Must Not Exceed)

| Operation | Target | Constraint |
|-----------|--------|-----------|
| PDF upload processing | 5 sec | NAS CPU (R1600) |
| Page rendering (JPEG) | 2 sec | Memory limit (4-16GB) |
| AI API call (Gemini) | 30 sec | Cloud API latency |
| Full batch processing (50 pages) | 2 min | End-user patience |
| Memory per concurrent job | <300MB | Cumulative heap |
| Disk I/O for split operations | <50MB/sec | NAS RAID latency |

### 5.2 Optimization Priorities

1. **Memory efficiency** (constrained NAS)
2. **API cost** (per-call charges from Gemini/Claude)
3. **Disk I/O** (NAS RAID performance)
4. **CPU efficiency** (shared R1600 processor)
5. **Network bandwidth** (cloud API traffic)

### 5.3 Profiling Before Optimizing

**NEVER optimize without data:**

```bash
# Profile with Pylance or Python's cProfile
python -m cProfile -o profile.stat your_script.py

# Analyze
python -m pstats profile.stat
> sort cumulative
> stats 20

# Measure improvements
pytest tests/performance/ --benchmark-only
```

---

## 6. Versioning & Release Strategy

### 6.1 Semantic Versioning

Format: `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)

- **MAJOR:** Breaking changes (API incompatible, requires migration)
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes (backward compatible)

### 6.2 Release Checklist

```
Before tagging a release:
- [ ] All PRs merged to main
- [ ] All tests passing (unit, integration, E2E)
- [ ] Security scan clean (bandit, safety)
- [ ] CHANGELOG.md updated
- [ ] Version bumped in pyproject.toml / package.json
- [ ] Release notes written (for users)
- [ ] Documentation updated
- [ ] Docker image built & tagged
- [ ] Deployed to staging; smoke tests passing
- [ ] Git tag created: git tag v1.2.3
- [ ] Docker image pushed to registry

Example CHANGELOG entry:
## v1.2.3 (2026-08-17)

### Features
- Support document classification via Gemini API (#42)
- Add UI controls for page rotation (#41)

### Bug Fixes
- Fix split boundary off-by-one error (#38)
- Handle corrupted PDFs gracefully (#37)

### Performance
- Cache thumbnail images (50% faster page load)
- Reduce API calls by 30% via local text extraction

### Breaking Changes
None

### Migration Guide
No migration needed; upgrade directly.
```

---

## 7. Documentation Maintenance

### 7.1 Update These Docs When:

**SYSTEM_SPECIFICATION.md:**
- New API endpoint added
- Architecture changes
- Technology stack updated
- Performance characteristics change
- Database schema modified

**WORKFLOW_TESTING_DEBUGGING.md:**
- New test category or tool introduced
- Debugging methodology refined
- CI/CD pipeline updated
- Performance benchmarks change

**DEPLOYMENT_MANAGEMENT_MANUAL.md:**
- New configuration option added
- Hardware requirement changes
- Deployment process updated
- Troubleshooting for new failure modes added

**AGENTS.md (this file):**
- Project principles evolve
- New tool constraints discovered
- Scope boundaries clarified
- Approval process changes

### 7.2 Documentation Style

- **Be concise:** Paragraphs <3 sentences; sections <500 words
- **Use examples:** Real code beats abstract descriptions
- **Link liberally:** Reference other docs; avoid duplication
- **Date entries:** When/why was this decided?
- **Version carefully:** Keep spec versions in sync

---

## 8. Communication & Decision-Making

### 8.1 Proposal Process

For features, architectural changes, or policy decisions:

1. **Open a GitHub Issue** with:
   - Clear problem statement (why?)
   - Proposed solution (how?)
   - Alternatives considered (what else could work?)
   - Impact on specs & CAVEMAN principles
   - Effort estimate

2. **Wait for Discussion** (target: <24 hours)
   - Stakeholders share concerns
   - Constraints clarified
   - Trade-offs discussed

3. **Refine Based on Feedback**
   - Update issue description
   - Adjust solution if needed
   - Request approval

4. **Approval & Implementation**
   - Issue labeled `approved`
   - Create PR; reference issue
   - Follow review process (section 2.3)

### 8.2 Escalation Path

**Level 1 (Unblock Yourself):**
- Ask in team Slack/Discord
- Search existing issues/PRs
- Review specs + comments

**Level 2 (Get Decision):**
- Open GitHub Issue
- Wait 24 hours for feedback
- Proceed if no objections

**Level 3 (Urgent Blocker):**
- Ping technical lead
- Schedule quick sync (15 min)
- Document decision in issue

---

## 9. CAVEMAN Principle Application Examples

### Example 1: Feature Request — "Add PDF Search Functionality"

**Request:** Users want to search text within uploaded PDFs

**CAVEMAN Analysis:**

- **Clarity:** Search logic is straightforward (Ctrl+F on extracted text)
- **Avoid:** Don't build full-text search DB; user PDF contains the text
- **Value:** Users can already search within PDF viewers; marginal ROI
- **Eagerness:** Could ship in 2 hours via simple in-memory search
- **Minimize:** No new dependencies; leverage existing text extraction
- **Agility:** Feedback will reveal if this is actually needed
- **Nudge:** Start with simple substring search; advance only if demanded
- **Mindfulness:** Trade-off = slight performance hit for convenience

**Decision:** Implement basic in-memory search (no indexing) as "nice-to-have," not core feature. Re-evaluate based on usage telemetry in 3 months.

### Example 2: Architecture Decision — "Microservices vs. Monolith"

**Question:** Should we split backend into separate services (OCR service, AI service, storage service)?

**CAVEMAN Analysis:**

- **Clarity:** Monolith is simpler to understand & debug
- **Avoid:** Microservices add complexity, operational burden (NAS deployment)
- **Value:** No user value from splitting (same functionality)
- **Eagerness:** Monolith deploys faster; easier to iterate
- **Minimize:** Monolith requires fewer containers, less config
- **Agility:** Easier to refactor monolith than re-architect services
- **Nudge:** If single service becomes bottleneck, split then (not speculative)
- **Mindfulness:** Trade-off = operational simplicity vs. independent scaling

**Decision:** Keep monolith. If CPU or memory becomes constraint, profile first. Only split if data proves it necessary.

### Example 3: Optimization — "Cache Thumbnails"

**Issue:** Thumbnail generation is slow on repeated page views

**CAVEMAN Analysis:**

- **Clarity:** Cache key is obvious (doc_id + page_num)
- **Avoid:** Don't build sophisticated cache invalidation; simple TTL is fine
- **Value:** 50% faster page load for users (measured)
- **Eagerness:** Implementation <4 hours; ship quickly
- **Minimize:** Use in-memory cache (no Redis); clear on re-analysis
- **Agility:** Remove cache if it causes issues; revert in 5 minutes
- **Nudge:** Start with 1-hour TTL; adjust based on usage
- **Mindfulness:** Trade-off = memory usage vs. speed; document limit

**Decision:** Implement in-memory LRU cache (Python `functools.lru_cache`); 100MB limit; 1-hour TTL. Measure memory impact in production. Remove if memory pressure rises.

---

## 10. Adherence Audit

### 10.1 How Specs Are Enforced

**Automated:**
- CI/CD pipeline runs linters, type checkers, security scanners
- Test coverage required >85%
- Branch protection requires all checks passing

**Manual:**
- Code review checklist (section 2.3)
- Weekly architecture review (architectural drift?)
- Monthly retrospectives (are CAVEMAN principles working?)

### 10.2 Measurement & Feedback

**Monthly Metrics:**
```
- Test coverage % (target: 85%+)
- CI pass rate (target: 99%+)
- Security scan findings (target: 0 critical)
- Average review cycle time (target: <2 days)
- Features shipped (track velocity)
- Production bugs (track regression rate)
- User satisfaction score (target: ≥4/5)
```

**Quarterly Retrospectives:**
- What worked well with CAVEMAN principles?
- What caused friction?
- Do principles need adjustment?
- Are we delivering value?

---

## 11. Final Authority

**This document supersedes all other guidance.**

If conflict arises between:
- AGENTS.md vs. specification → Specs take precedence (built-in specs)
- CAVEMAN principles vs. timeline → CAVEMAN applies (quality non-negotiable)
- Individual preference vs. established patterns → Patterns apply (consistency matters)

**Changes to AGENTS.md require:**
- GitHub Issue discussion
- Technical lead approval
- Documentation update
- Team communication

---

## Appendix A: Quick Reference Card

**Before coding:**
- [ ] Read relevant spec section
- [ ] Check existing implementation
- [ ] Plan tests
- [ ] Estimate effort

**While coding:**
- [ ] Follow style guide
- [ ] Write tests alongside code
- [ ] Type-hint everything
- [ ] Comment the "why"

**Before committing:**
- [ ] All tests pass
- [ ] Linters/type checker pass
- [ ] Security scan clean
- [ ] Coverage maintained
- [ ] Docs updated

**Before merging:**
- [ ] PR reviewed & approved
- [ ] CI passes
- [ ] CHANGELOG updated
- [ ] Release notes (if applicable)

---

## Appendix B: CAVEMAN Principles Decision Tree

```
Am I building a feature?
├─ Does spec say to build it? [YES] → OK, continue
└─ [NO] → STOP. Open issue first; get approval.

Is my solution simple & clear?
├─ [YES] → OK, proceed
└─ [NO] → Simplify or break into smaller tasks

Do I need new dependencies?
├─ [YES] → Justify in PR; get approval
└─ [NO] → Great, proceed

Can I ship 80% in <1 day?
├─ [YES] → Ship it; iterate based on feedback
└─ [NO] → Break into smaller tasks

Are my tests comprehensive?
├─ [YES] → OK to merge
└─ [NO] → Add more tests before merging

Is everyone clear on trade-offs?
├─ [YES] → Document & proceed
└─ [NO] → Discuss before implementing
```

---

## Appendix C: Glossary of Terms

- **CAVEMAN:** Development manifesto guiding all decisions
- **Spec:** One of three reference documents (System, Workflow, Deployment)
- **YAGNI:** "You Aren't Gonna Need It" — build what's needed now
- **TDD:** Test-Driven Development — tests before code
- **PR:** Pull Request — code review mechanism
- **Regression:** Unintended behavior change from new code
- **Trade-off:** Explicit cost-benefit decision (documented, communicated)
- **Scope Creep:** Adding features beyond original plan (AVOID)
- **Backward Compatible:** New version doesn't break old code/data

---

**Last Updated:** 2026-08-17  
**Maintained By:** Technical Leads  
**Revision Cycle:** Quarterly review + as needed  
**Questions?** Open a GitHub Issue
