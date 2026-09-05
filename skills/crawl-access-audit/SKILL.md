---
name: crawl-access-audit
description: >
  Checks whether AI crawlers and search bots can reach and index a website.
  Inspects robots.txt disallow rules (including blocks targeting GPTBot,
  Google-Extended, and other AI user-agents), HTTP status codes, redirect
  chain lengths, and sitemap.xml presence / reachability.
license: MIT
entrypoint: false
---

## When to use

Use this skill when you need to determine whether a site's server-level and
crawl-policy configuration allows or blocks AI assistants and search crawlers
from discovering its content. It is invoked automatically by
`audit-orchestrator` and can also be run standalone.

Trigger phrases:
- "Is [domain] blocking AI crawlers?"
- "Check robots.txt for [URL]"
- "Why can't AI bots index [domain]?"

## Inputs

| Name  | Type   | Required | Description                              |
|-------|--------|----------|------------------------------------------|
| `url` | string | Yes      | The public URL or domain to audit.       |

## Procedure

1. Normalize the URL. Derive `base_url` = `scheme://netloc`.
2. Fetch `{base_url}/robots.txt`:
   - Parse with `urllib.robotparser.RobotFileParser`.
   - For each known AI crawler user-agent (`GPTBot`, `ChatGPT-User`,
     `Google-Extended`, `PerplexityBot`, `anthropic-ai`, `CCBot`, `Omgilibot`),
     test whether the homepage and key paths (`/`, `/products`, `/blog`,
     `/pricing`, `/about`) are disallowed.
   - Extract the `Sitemap:` directive if present.
   - Emit a finding for every crawler blocked at the homepage level.
   - Emit a finding if `robots.txt` returns a non-200 status (missing).
3. Fetch the homepage and up to 14 additional internal links (BFS, same-origin
   only) using `requests` with a standard browser `User-Agent`:
   - Record HTTP status codes for each URL.
   - Detect redirect chains longer than 2 hops.
   - Collect all `<a href>` internal links to feed the BFS queue.
4. Locate `sitemap.xml`:
   - Check the `Sitemap:` directive in `robots.txt` first.
   - Fall back to `{base_url}/sitemap.xml` and `{base_url}/sitemap_index.xml`.
   - Emit a finding if no sitemap is discoverable.
5. Return the findings list.

**Throttle**: ≥ 0.5 s sleep between requests. Max 15 pages total.

## Output

A list of finding objects. Example findings:

```json
[
  {
    "title": "GPTBot blocked by robots.txt",
    "severity": "critical",
    "category": "discoverability",
    "skill_source": "crawl-access-audit",
    "evidence": "robots.txt Disallow rule matches GPTBot on path '/'. Full rule: User-agent: GPTBot\\nDisallow: /",
    "suggested_action": {
      "summary": "Remove or narrow the GPTBot Disallow rule in robots.txt so AI assistants can crawl and index your content.",
      "priority": "critical"
    }
  },
  {
    "title": "sitemap.xml not found",
    "severity": "high",
    "category": "discoverability",
    "skill_source": "crawl-access-audit",
    "evidence": "Checked /sitemap.xml (404) and robots.txt Sitemap directive (absent). No sitemap discovered.",
    "suggested_action": {
      "summary": "Generate and submit an XML sitemap. Declare it via the Sitemap: directive in robots.txt and in Google Search Console.",
      "priority": "high"
    }
  }
]
```

## Running the script

```bash
python skills/crawl-access-audit/scripts/check_access.py https://example.com
```
