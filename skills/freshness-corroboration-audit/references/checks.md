# Freshness & Corroboration Audit — Check Reference

This checklist is executed by `check_freshness.py`.
Validates internal fact consistency and content freshness signals.

## Fact extraction patterns

### Phone numbers
```regex
\+?1?\s*[-.]?\s*\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b      # North American
\+\d{1,3}[\s.-]\d{3,4}[\s.-]\d{3,4}(?:[\s.-]\d{3,4})?    # International
```
Normalize to digits-only (strip country code 1 prefix) before comparison.

### Email addresses
```regex
\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b
```
Exclude: example.*, test@*, user@* (placeholder addresses).

### Physical addresses
```regex
\b\d{1,5}\s+[A-Z][a-zA-Z\s]{2,30}(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Hwy)\b
```

### Prices
```regex
(?:USD\s*)?\$\s*[\d,]+(?:\.\d{2})?   # USD
€\s*[\d,]+(?:\.\d{2})?               # EUR
£\s*[\d,]+(?:\.\d{2})?               # GBP
```

## JSON-LD fact extraction (in addition to regex)
```
telephone → normalize → compare
address.streetAddress + addressLocality + postalCode → join → compare  
email → lowercase → compare
```

## Freshness signal sources (per page)

| Source | Field | Notes |
|---|---|---|
| JSON-LD | `dateModified` | Highest trust |
| JSON-LD | `datePublished` | Useful for articles |
| JSON-LD | `dateCreated` | Lowest preference |
| `<meta>` | `article:modified_time` | OpenGraph standard |
| `<meta>` | `article:published_time` | OpenGraph |
| `<meta>` | `og:updated_time` | OpenGraph |
| `<meta>` | `last-modified` | HTTP meta |

## Consistency finding thresholds

| Check | Condition | Severity |
|---|---|---|
| Phone variants | ≥ 2 distinct normalized values across pages | high |
| Email variants | > 2 distinct addresses (some variance OK) | medium |
| Address variants | ≥ 2 distinct canonical strings | high |
| No freshness signals | 0/N pages have any date field | high |
| Stale content | Most recent date > 365 days ago | medium |
| Sparse freshness | < 50% of pages have date signals | medium |

## Priority crawl paths for fact extraction

```
/contact, /about, /about-us, /company, /pricing,
/faq, /help, /support, /location, /store
```

## Evidence format

```
"Found 2 distinct phone numbers: '+18005550100' on /contact and /footer; 
 '+18005550199' on /about. Checked 15 pages total."
```

```
"0/12 pages contain dateModified, datePublished (JSON-LD), 
 article:modified_time, or og:updated_time. AI crawlers cannot determine content currency."
```
