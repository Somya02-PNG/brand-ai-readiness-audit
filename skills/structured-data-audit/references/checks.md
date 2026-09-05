# Structured Data Audit — Check Reference

This checklist is executed by `check_schema.py`.
Uses extruct (and BeautifulSoup fallback) to extract JSON-LD, Microdata, and OpenGraph.

## Coverage thresholds

| Condition | Threshold | Severity |
|---|---|---|
| Pages with zero JSON-LD | ≥ 80% of sample | critical |
| Pages with zero JSON-LD | ≥ 50% of sample | high |
| Malformed JSON in ld+json block | Any parse error | high |
| Wrong @context value | Not "https://schema.org" or "http://schema.org" | medium |

## Required properties per schema type

### Organization / LocalBusiness / Corporation
```
REQUIRED:  name, url
HIGH-VALUE: description, sameAs, legalName, logo, telephone, address
```

### Product
```
REQUIRED:  name, description, offers
OFFERS REQUIRED: price, priceCurrency, availability
HIGH-VALUE: image, brand, sku, review
```

### Article / BlogPosting / NewsArticle
```
REQUIRED:  headline, datePublished, author
HIGH-VALUE: dateModified, image, description, publisher
```

### FAQPage
```
REQUIRED:  mainEntity (non-empty list)
EACH ITEM: name (question), acceptedAnswer.text
```

### BreadcrumbList
```
REQUIRED:  itemListElement (non-empty)
```

### LocalBusiness
```
REQUIRED:  name, address, telephone
HIGH-VALUE: openingHours, geo, priceRange
```

### Event
```
REQUIRED:  name, startDate
HIGH-VALUE: location, description, organizer
```

### WebSite
```
REQUIRED:  name, url
HIGH-VALUE: potentialAction (SearchAction for sitelinks search box)
```

## URL priority for crawl sample (up to 12 pages)

Score higher → crawled first:
```
/product*, /shop*, /item*, /buy*     ← Product schema targets
/blog*, /article*, /post*, /news*    ← Article schema targets
/about*, /company*, /team*           ← Organization targets
/faq*, /help*, /support*             ← FAQPage targets
/pricing*, /plans*                   ← Pricing/Offer targets
/contact*                            ← LocalBusiness targets
```

## extruct usage

```python
import extruct
data = extruct.extract(
    html_bytes,
    base_url=url,
    syntaxes=["json-ld", "microdata", "opengraph"],
    uniform=True,
)
# data["json-ld"] → list of dicts (normalized)
# data["microdata"] → list of dicts
# data["opengraph"] → dict of og: properties
```

## Evidence format

```
"Sampled 12 product pages (URLs: /products/alpha, /products/beta, ...); 
 0/12 contained any JSON-LD block."
```

```
"Page https://example.com/: Organization JSON-LD present but missing required 
 fields: description, sameAs. Present: name, url."
```

```
"Malformed JSON in <script type='application/ld+json'> on /blog/post-1: 
 json.JSONDecodeError: Expecting ',' delimiter: line 4 column 12"
```
