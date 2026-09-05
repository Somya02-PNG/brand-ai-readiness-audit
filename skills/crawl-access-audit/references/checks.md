# Crawl Access Audit — Check Reference

This checklist is executed by `check_access.py`. Each row maps to a finding severity.

## robots.txt checks

| Check | Pass condition | Severity if fail |
|---|---|---|
| robots.txt reachable | `GET /robots.txt` returns HTTP 200 | medium |
| GPTBot not blocked at `/` | `rp.can_fetch("GPTBot", base_url + "/")` is True | critical |
| ChatGPT-User not blocked | `rp.can_fetch("ChatGPT-User", ...)` is True | critical |
| Google-Extended not blocked | `rp.can_fetch("Google-Extended", ...)` is True | high |
| PerplexityBot not blocked | `rp.can_fetch("PerplexityBot", ...)` is True | high |
| anthropic-ai not blocked | `rp.can_fetch("anthropic-ai", ...)` is True | high |
| CCBot not blocked | `rp.can_fetch("CCBot", ...)` is True | medium |
| Omgilibot not blocked | `rp.can_fetch("Omgilibot", ...)` is True | medium |
| Googlebot not blocked | `rp.can_fetch("Googlebot", ...)` is True | high |

## HTTP status checks

| Check | Pass condition | Severity if fail |
|---|---|---|
| Homepage returns 200 | Final status after redirects == 200 | critical |
| No redirect chain > 2 hops | `len(chain) <= 2` | medium |
| No 5xx on crawled pages | All sampled pages return < 500 | high |
| No 4xx on homepage | Homepage not 4xx | critical |

## Sitemap checks

| Check | Pass condition | Severity if fail |
|---|---|---|
| Sitemap discoverable | Found via `robots.txt Sitemap:` directive OR `/sitemap.xml` (200) OR `/sitemap_index.xml` (200) | high |
| Sitemap parseable | XML is valid, contains at least 1 `<url>` | medium |

## Crawler user-agents tested

```
GPTBot              OpenAI GPT crawler
ChatGPT-User        ChatGPT browsing plugin
Google-Extended     Google AI training crawler
PerplexityBot       Perplexity AI crawler
anthropic-ai        Anthropic Claude crawler
CCBot               Common Crawl (many LLM training sets)
Omgilibot           Webz.io AI crawler
Googlebot           Google Search (baseline — if even this is blocked, it's critical)
```

## Key paths to test in robots.txt

```
/               (homepage)
/products       (product index)
/blog           (content index)
/pricing        (conversion page)
/about          (entity clarity page)
/faq            (FAQPage schema target)
/shop           (e-commerce root)
```

## Evidence format

```
"robots.txt Disallow rule prevents GPTBot from accessing: /. 
 Rule text: User-agent: GPTBot\nDisallow: /"
```

```
"sitemap.xml not discoverable. Checked: /sitemap.xml (404), 
 /sitemap_index.xml (404). No Sitemap: directive in robots.txt."
```
