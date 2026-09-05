---
name: structured-data-audit
description: >
  Checks for the presence, JSON validity, and completeness of schema.org
  JSON-LD markup on a representative sample of pages. Validates required
  properties for Organization, Product, Article, FAQPage, BreadcrumbList,
  and LocalBusiness types. Flags missing markup, malformed JSON, and
  incomplete required fields that reduce AI citation quality.
license: MIT
entrypoint: false
---

## When to use

Use this skill when you want to assess whether a site provides structured
metadata that allows AI assistants and search engines to understand and
confidently cite its content.

Trigger phrases:
- "Does [domain] have structured data / schema markup?"
- "Check JSON-LD on [URL]"
- "Why isn't [brand] showing rich results in search?"

## Inputs

| Name  | Type   | Required | Description                        |
|-------|--------|----------|------------------------------------|
| `url` | string | Yes      | The public URL or domain to audit. |

## Procedure

1. Crawl homepage + up to 11 representative pages (BFS same-origin, cap 12
   total). Prioritize URLs matching patterns like `/product`, `/blog`, `/about`,
   `/faq`, `/pricing`, `/contact`.
2. For each page, extract all `<script type="application/ld+json">` blocks.
3. Attempt `json.loads()` on each block:
   - If parsing fails → emit a `high`-severity malformed-JSON finding with the
     first parse error and URL.
4. For successfully parsed blocks, read `@type` (handle arrays):
   - **Organization**: require `name`, `url`, `description`, `sameAs`.
   - **Product**: require `name`, `description`, `offers` (with `price`,
     `priceCurrency`).
   - **Article**: require `headline`, `datePublished`, `author`.
   - **FAQPage**: require `mainEntity` (non-empty array with `name`/`acceptedAnswer`).
   - **LocalBusiness**: require `name`, `address`, `telephone`.
   - **BreadcrumbList**: require `itemListElement` (non-empty).
   - All other types: confirm at least `name` is present.
5. Emit a finding per missing required property (group by page where multiple
   properties are missing from the same type).
6. Count pages with zero JSON-LD markup. If > 50% of sampled pages lack
   markup entirely, emit a `critical`-severity summary finding.
7. Check for `@context` presence and correct value (`https://schema.org` or
   `http://schema.org`).

## Output

Example findings:

```json
[
  {
    "title": "0 of 12 product pages contain schema.org markup",
    "severity": "critical",
    "category": "discoverability",
    "skill_source": "structured-data-audit",
    "evidence": "Sampled 12 product pages (URLs: /products/alpha, /products/beta, ...); 0/12 contained any <script type='application/ld+json'> block.",
    "suggested_action": {
      "summary": "Add Product + Offer JSON-LD to every product page. At minimum include: name, description, offers.price, offers.priceCurrency, offers.availability.",
      "priority": "critical"
    }
  },
  {
    "title": "Organization schema missing 'sameAs' on homepage",
    "severity": "medium",
    "category": "discoverability",
    "skill_source": "structured-data-audit",
    "evidence": "Homepage (https://example.com/) has Organization JSON-LD but no 'sameAs' array. Present fields: name, url.",
    "suggested_action": {
      "summary": "Add a 'sameAs' array to your Organization JSON-LD pointing to verified profiles: LinkedIn, Twitter/X, Wikidata, Crunchbase.",
      "priority": "medium"
    }
  }
]
```

## Running the script

```bash
python skills/structured-data-audit/scripts/check_schema.py https://example.com
```
