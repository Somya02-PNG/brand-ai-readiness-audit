# Entity Clarity Audit — Check Reference

This checklist is executed by `check_entity.py`.
Verifies that the brand has sufficient signals to be correctly identified by AI knowledge graphs.

## sameAs checks

| Check | Condition | Severity |
|---|---|---|
| sameAs present anywhere | Any JSON-LD entity has `sameAs` property | high if absent |
| High-trust anchors | sameAs includes Wikidata or Wikipedia | medium if absent |
| Crunchbase present | sameAs includes crunchbase.com | medium if absent |

### High-trust disambiguator domains

```
wikidata.org      (highest trust — used by all major AI knowledge graphs)
wikipedia.org     (narrative identity)
crunchbase.com    (business entity data)
```

### Social/authority platform domains

```
linkedin.com      (professional identity)
twitter.com / x.com
facebook.com
instagram.com
youtube.com
github.com
glassdoor.com
g2.com
trustpilot.com
yelp.com
producthunt.com
angellist.com / wellfound.com
pitchbook.com
```

## legalName check

| Check | Condition | Severity |
|---|---|---|
| `legalName` in Organization JSON-LD | Field present and non-empty | medium if absent |
| Organization JSON-LD exists at all | Any page has @type=Organization | high if absent |

## About page scoring (6 categories)

Score ≥ 3/6 → pass. Score < 3/6 → `low` severity finding.

```
founding_year    → /\b(?:founded|established|incorporated|since|est\.?)\s+(?:in\s+)?\d{4}\b/i
location_hq      → /\b(?:headquartered|based|located)\s+in\s+[A-Z][a-zA-Z\s,]+/i
industry_vertical → /\b(?:software|saas|e-commerce|healthcare|fintech|edtech|b2b|b2c|marketplace|platform|agency|consulting|manufacturing|retail)\b/i
team_size        → /\b\d+[,\d]*\s+(?:employees|team members|people|professionals)\b/i
customer_count   → /\b\d+[,\d]*\+?\s+(?:customers|clients|users|brands|businesses)\b/i
geographic_reach → /\b\d+\s+(?:countries|regions|cities|markets)\b/i
```

## About page candidate paths (checked in order)

```
/about, /about-us, /company, /who-we-are,
/our-story, /team, /mission
```

## External link scan

All crawled pages are scanned for outbound links matching authority platform domains.
If zero outbound links to any known authority/social platform → `medium` severity.

## Evidence format

```
"Crawled 12 pages including homepage and /about. 
 0 pages contain 'sameAs' in any JSON-LD entity. 
 Without sameAs, AI knowledge graphs cannot link this site to verified external identity."
```

```
"sameAs found: linkedin.com, twitter.com. 
 Missing high-trust anchors: Wikidata, Wikipedia, Crunchbase."
```

```
"About page score: 1/6 disambiguating facts detected (industry_vertical). 
 Missing: founding_year, location_hq, team_size, customer_count, geographic_reach."
```
