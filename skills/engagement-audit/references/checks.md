# Engagement Audit — Check Reference

This checklist is executed by `check_engagement.py`.
Evaluates on-site signals that determine whether visitors who arrive from AI recommendations
stay, explore, and convert.

## Broken internal links

| Condition | Severity |
|---|---|
| > 20% of internal links return 4xx/5xx | critical |
| > 10% | high |
| > 5% | medium |
| Any broken links | low (if < 5%) |

**Method**: HEAD request per unique internal URL (fall back to GET if 405).
**Cap**: check up to 80 unique targets for time budget.

## Dead-end pages

| Condition | Severity |
|---|---|
| ≥ 1 non-homepage crawled page has 0 outbound internal links | medium |

A dead-end page is one where `count(<a href> pointing to same-origin URL) == 0`.

## Navigation structure

| Check | Pass condition | Severity if fail |
|---|---|---|
| `<nav>` element present on homepage | `bool(soup.find("nav"))` is True | high |
| Navigation depth ≤ 3 levels | Max nested `<ul>/<li>` depth ≤ 3 | medium |

Navigation depth algorithm:
```
def ul_depth(tag, depth):
    for child in tag.children:
        if child.name in ("ul", "ol"):
            return ul_depth(child, depth + 1)
    return depth
max_depth = max(ul_depth(nav, 0) for nav in soup.find_all("nav"))
```

## Above-fold orientation (homepage only)

| Check | Pass condition | Severity if fail |
|---|---|---|
| `<h1>` present | `bool(soup.find("h1"))` is True | high |
| CTA keyword in first 25% of body HTML | Any CTA keyword found in `body_html[:len//4].lower()` | medium |

### CTA keyword list

```
get started, start free, sign up, signup, try for free, try free,
free trial, buy now, shop now, order now, add to cart,
learn more, see how, request demo, book demo, schedule demo,
contact us, get in touch, talk to us, speak to, reach out,
download, get the app, install, watch demo, see demo,
explore, discover, view plans, see pricing
```

## Wayfinding elements (sites with ≥ 5 crawled pages)

| Check | Detection method | Severity if absent |
|---|---|---|
| Breadcrumbs | `aria-label="breadcrumb"` OR `.breadcrumb` class OR BreadcrumbList JSON-LD OR `itemtype` BreadcrumbList | low |
| Site search | `<input type="search">` OR `role="search"` OR `aria-label` containing "search" | low |

## Evidence format

```
"Discovered 82 unique internal links; 28/82 (34.1%) returned HTTP 4xx. 
 Sample broken URLs: /old-pricing, /team/john-doe, /blog/2022/post-title."
```

```
"Homepage (https://example.com/) raw HTML contains 0 <h1> elements."
```

```
"Navigation has 4 nested <ul>/<li> levels in <nav>. 
 Deep navigation is hard to scan and parse as a site structure signal."
```

```
"3 pages with 0 outbound internal links (dead ends): 
 /old-landing, /promo/2024, /404-page."
```
