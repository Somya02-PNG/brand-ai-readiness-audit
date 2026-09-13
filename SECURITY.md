# Security Policy & Operational Safety Guardrails

The **Brand AI-Readiness Audit Marketplace** is designed from the ground up as a passive, non-destructive, read-only diagnostic system. It inspects public web properties without modifying, altering, stressing, or degrading target web infrastructure.

---

## Operational Safety Guardrails

### 1. Read-Only, GET-Only
- All network communications initiated by the audit suite are strictly restricted to standard read-only HTTP `GET` and `HEAD` requests.
- No state-mutating HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`) are ever generated or sent.
- Form fields, login inputs, and transaction endpoints are never submitted or triggered.

### 2. `robots.txt` Reporting vs. Tool Fetch Behaviour

The `crawl-access-audit` worker reads and parses the target site's `robots.txt` and **reports** any disallow rules that would block known AI crawlers (GPTBot, ClaudeBot, etc.) as audit **findings** — this is the core diagnostic output of that worker.

The audit tool's **own** page-sampling fetches use a bounded, low-volume, rate-limited HTTP GET pattern (≤20 fetches per worker, 0.3–0.5 s polite delay between requests, standard browser-like `User-Agent` headers). However, the tool does **not** currently self-gate every fetch against `robots.txt` before sending it. This means the tool may sample pages that a strict `robots.txt` disallow rule would block for crawlers.

> **Known Limitation**: Self-gating the audit tool's own fetches against `robots.txt` is a planned improvement for a future version. Until then, operators should be aware that the audit performs read-only, low-volume sampling regardless of `robots.txt` disallow directives targeting third-party bots. The tool never submits forms, mutates state, or exceeds the per-worker fetch cap.

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
