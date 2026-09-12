# Security Policy & Operational Safety Guardrails

The **Brand AI-Readiness Audit Marketplace** is designed from the ground up as a passive, non-destructive, read-only diagnostic system. It inspects public web properties without modifying, altering, stressing, or degrading target web infrastructure.

---

## Operational Safety Guardrails

### 1. Read-Only, GET-Only
- All network communications initiated by the audit suite are strictly restricted to standard read-only HTTP `GET` and `HEAD` requests.
- No state-mutating HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`) are ever generated or sent.
- Form fields, login inputs, and transaction endpoints are never submitted or triggered.

### 2. Respects `robots.txt`
- All crawling operations strictly adhere to `robots.txt` directives per the RFC 9309 specification.
- If a target domain disallows AI crawlers or audit user-agents from accessing specific paths or the entire site, the crawlers honor the rule, report the disallow rule in audit findings, and never attempt to bypass or override the restriction.
- Any crawl delay or rate-limiting parameters declared in `robots.txt` are respected.

### 3. No Authenticated Areas
- The marketplace inspects only publicly accessible web content.
- The system does not accept, store, handle, or forward any authentication credentials, passwords, session tokens, API keys, or OAuth secrets.
- It will never attempt credential stuffing, authentication bypass, session hijacking, or administrative privilege escalation.

### 4. No Site-Altering Actions
- The marketplace functions strictly as a client-side reader.
- It makes zero mutations to remote server state, databases, file storage, or DNS records.
- Headless browser rendering (via Playwright) runs in an ephemeral, isolated sandbox where JavaScript execution is restricted solely to rendering the DOM for textual comparison. No cookies, local storage mutations, or sessions persist.

### 5. Per-Worker Fetch Cap of 20
- To prevent denial-of-service risks or performance degradation on target websites, strict resource limits are enforced:
  - **Per-Worker Fetch Cap**: Each individual worker script enforces a hard cap of at most 20 page fetches per audit run.
  - **Link Cap on Dense Pages**: When auditing pages with high link density (>100 internal links), queueing is strictly capped at 20 fetches, and the cap is recorded directly in the finding evidence.
  - **Polite Crawl Throttling**: A deliberate delay of 0.3s to 0.5s is maintained between sequential HTTP requests.
  - **Bounded Concurrency**: Headless DOM rendering is restricted to a maximum of 4 concurrent page contexts.

---

## Reporting a Security Vulnerability

If you identify an unintended crawl behavior, safety issue, or potential vulnerability in this repository:

1. **Do not** open a public issue.
2. Contact the maintainers directly through private GitHub security advisory channels.
3. Include detailed reproduction steps, target URLs, and relevant console traces.
4. Maintainers will review and respond promptly to coordinate responsible disclosure.
