# Security Policy & Safety Guardrails

The **Brand AI-Readiness Audit Marketplace** is designed from the ground up as a safe, passive, non-destructive diagnostic system. It inspects public web properties without altering, degrading, or stressing target infrastructure.

---

## Safety & Operational Guardrails

### 1. Read-Only GET Operations Only
- Every audit operation is restricted strictly to standard HTTP `GET` and `HEAD` requests.
- No state-modifying HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`) are ever sent.
- The system does not attempt form submissions, simulated checkout flows, or transactional interactions that could alter server data or generate mock orders.

### 2. Strict Compliance with `robots.txt`
- All crawling operations respect `robots.txt` directives per RFC 9309.
- If a target site disallows auditing user-agents on specific paths or site-wide, the crawlers honor the rule, record the disallow directive in findings, and do not attempt to bypass the restriction.
- Crawlers respect `Crawl-delay` parameters where specified.

### 3. No Authentication or Credential Access
- The marketplace audits only publicly accessible web content.
- It does not accept, request, store, or forward login credentials, API tokens, session cookies, OAuth secrets, or administrative credentials.
- It will never attempt authentication bypass, credential stuffing, SQL injection, fuzzing, or vulnerability exploitation.

### 4. Zero Site-Altering Actions
- The marketplace operates purely as a client-side reader.
- It does not upload files, write to server storage, modify DNS records, execute administrative commands, or trigger destructive API endpoints.
- Browser automation (Playwright) runs in an isolated, ephemeral sandbox with JavaScript execution strictly bounded to page rendering. No cookies or cached credentials persist after session termination.

### 5. Bounded Per-Worker Fetch Caps
To prevent excessive load or Denial of Service (DoS) risks to audited domains, strict resource and crawl bounds are hardcoded across all worker scripts:
- **Maximum Page Samples**: Each worker script crawls at most 15–20 representative pages per audit run.
- **Link Cap on Dense Pages**: When encountering pages with over 100 internal links, link queuing is explicitly capped at 20 fetches, and the cap is recorded in the finding evidence.
- **Polite Crawl Throttling**: A minimum throttle delay (0.3s to 0.5s) is enforced between successive HTTP requests.
- **Playwright Concurrency Cap**: Headless DOM rendering is capped at a maximum of 4 concurrent page contexts within a single browser instance, and bounded by strict timeouts (12–15s).

---

## Reporting a Security Vulnerability

If you identify any security issue, unintended crawl behavior, or potential risk in this codebase:

1. Do **not** open a public issue.
2. Email the maintainers directly at `security@brand-ai-readiness-audit.org` (or contact project maintainers through private GitHub advisory channels).
3. Include details of the vulnerability, steps to reproduce, and any relevant log traces.
4. Maintainers will review and respond within 48 hours to coordinate remediation.
