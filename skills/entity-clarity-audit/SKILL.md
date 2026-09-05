---
name: entity-clarity-audit
description: >
  Checks whether a brand has sufficient disambiguating identity signals to
  prevent AI assistants from confusing it with other entities that share a
  similar name. Inspects sameAs links to verified external profiles, explicit
  legal/brand name declarations, About page identity statements, and unique
  identifiers such as LinkedIn, Wikidata, Crunchbase, and GitHub.
license: MIT
entrypoint: false
---

## When to use

Use this skill when a brand suspects it is being misidentified, ignored, or
conflated with another entity of similar name by AI assistants.

Trigger phrases:
- "Is [brand] clearly identified for AI assistants?"
- "Why does AI confuse [brand] with a different company?"
- "Check entity clarity for [domain]"
- "Does [site] have enough identity signals?"

## Inputs

| Name  | Type   | Required | Description                        |
|-------|--------|----------|------------------------------------|
| `url` | string | Yes      | The public URL or domain to audit. |

## Procedure

1. Crawl homepage, `/about`, `/about-us`, `/company`, `/who-we-are` (if they
   exist, 404 gracefully). Also crawl up to 10 additional pages (BFS).
2. **sameAs audit**:
   - Search all JSON-LD blocks for `sameAs` arrays.
   - Check for links pointing to: `linkedin.com`, `twitter.com`, `x.com`,
     `facebook.com`, `instagram.com`, `youtube.com`, `wikidata.org`,
     `wikipedia.org`, `crunchbase.com`, `github.com`, `g2.com`, `glassdoor.com`.
   - Emit a `high`-severity finding if no `sameAs` property exists anywhere.
   - Emit a `medium`-severity finding if `sameAs` exists but no Wikidata/
     Wikipedia/Crunchbase link is present (these are the highest-trust
     disambiguators for AI).
3. **Legal/brand name**:
   - Search for the `legalName` property in Organization JSON-LD.
   - Search homepage and About page text for trademark symbols (™, ®) adjacent
     to brand name tokens.
   - Emit a `medium`-severity finding if no `legalName` is declared in JSON-LD.
4. **About page identity statement**:
   - Check whether `/about` (or equivalent) exists and contains an identity
     paragraph mentioning the company's founding year, location, or industry.
   - Presence of specific disambiguating facts (year, HQ city, industry) is
     scored — emit a `low`-severity finding if the About page is too generic
     (< 3 disambiguating facts detected).
5. **External identifier links** (non-social):
   - Scan all crawled pages for outbound links to known identifier platforms:
     Wikidata (`wikidata.org/wiki/Q`), Crunchbase, LinkedIn company pages.
   - Emit a finding if none found.

## Output

Example findings:

```json
[
  {
    "title": "No sameAs links in any JSON-LD block",
    "severity": "high",
    "category": "discoverability",
    "skill_source": "entity-clarity-audit",
    "evidence": "Crawled 12 pages including homepage and /about. 0/12 pages contain a 'sameAs' property in JSON-LD. Without sameAs, AI knowledge graphs cannot reliably link this site to its external identity.",
    "suggested_action": {
      "summary": "Add a sameAs array to your Organization JSON-LD on the homepage pointing to your LinkedIn company page, Wikidata entry (create one if needed), and Crunchbase profile.",
      "priority": "high"
    }
  },
  {
    "title": "No legalName declared in Organization JSON-LD",
    "severity": "medium",
    "category": "discoverability",
    "skill_source": "entity-clarity-audit",
    "evidence": "Organization JSON-LD on homepage contains 'name: Acme' but no 'legalName' field. Brand name 'Acme' is highly ambiguous (used by many unrelated companies).",
    "suggested_action": {
      "summary": "Add 'legalName' to your Organization JSON-LD with your full registered company name (e.g., 'Acme Corporation Inc.').",
      "priority": "medium"
    }
  }
]
```

## Running the script

```bash
python skills/entity-clarity-audit/scripts/check_entity.py https://example.com
```
