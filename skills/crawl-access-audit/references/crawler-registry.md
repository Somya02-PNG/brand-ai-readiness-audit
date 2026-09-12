# AI Crawler Registry

A comprehensive reference of known artificial intelligence (AI) crawlers, search indexers, user-agent browsing bots, and data collection spiders. This registry documents the operating entity, operational purpose, and robots.txt parsing and compliance behaviors for each bot.

---

## Quick Reference Matrix

| Crawler User-Agent | Operator | Primary Purpose | Category | Robots.txt Behavior |
|---|---|---|---|---|
| **GPTBot** | OpenAI | Foundation LLM training (GPT-4, GPT-Next) | Training | Strictly respects `User-agent: GPTBot` and `*`. Does not execute JavaScript. |
| **OAI-SearchBot** | OpenAI | Search indexing for ChatGPT Search & SearchGPT | Search Index | Respects `User-agent: OAI-SearchBot`. Does not use content for model training. |
| **ChatGPT-User** | OpenAI | Real-time browsing triggered by end-user requests | User Action | Respects `User-agent: ChatGPT-User` and `*`. Fetches on-demand user queries. |
| **PerplexityBot** | Perplexity AI | Indexing web content for conversational answers | Search Index | Respects `User-agent: PerplexityBot` and `*`. Indexes content for citations. |
| **Perplexity-User** | Perplexity AI | On-demand live retrieval for specific user queries | User Action | Respects `User-agent: Perplexity-User` and `*`. |
| **ClaudeBot** | Anthropic | Training data collection for Claude models | Training | Respects `User-agent: ClaudeBot` and `*`. Respects `Allow` / `Disallow`. |
| **anthropic-ai** | Anthropic | Legacy/alternate crawler for Anthropic data collection | Training | Respects `User-agent: anthropic-ai` and `*`. |
| **Claude-Web** | Anthropic | Real-time web retrieval for live Claude user sessions | User Action | Respects `User-agent: Claude-Web` and `*`. |
| **Google-Extended** | Google | Controls content training for Gemini and Vertex AI | Training Control | Standalone token. Disallowing excludes Gemini training without impacting Googlebot search. |
| **CCBot** | Common Crawl | Web archiving; primary data source for open LLMs | Archive / Training | Strictly respects `User-agent: CCBot`, `*`, and `Crawl-delay`. |
| **Bytespider** | ByteDance | Model training & search index for TikTok/Douyin | Training / Search | Respects `User-agent: Bytespider` and `*`. Fast crawl rates. |
| **Applebot-Extended** | Apple | Controls training data for Apple Intelligence | Training Control | Standalone token. Disallowing excludes Apple AI training without hurting Siri/Spotlight search. |
| **meta-externalagent** | Meta | Data collection for Llama models and Meta AI | Training | Respects `User-agent: meta-externalagent` and `*`. |
| **cohere-ai** | Cohere | Training data for Cohere enterprise models & embeddings | Training | Respects `User-agent: cohere-ai` and `*`. |
| **Omgilibot** | Webz.io | Commercial data feed crawler for AI training sets | Training Feed | Respects `User-agent: Omgilibot` and `*`. |
| **Googlebot** | Google | General Google Search index (baseline reference) | Search Index | Respects `User-agent: Googlebot` and `*`. Executes JavaScript. |

---

## Detailed Crawler Profiles

### 1. GPTBot
- **Operator**: OpenAI
- **User-Agent Token**: `GPTBot`
- **Example User-Agent String**: `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)`
- **Purpose**: Crawls web content to train OpenAI's foundation models (e.g., GPT-4, GPT-4o). Content collected by GPTBot is incorporated into pre-training and fine-tuning datasets.
- **Robots.txt Behavior**: Respects `User-agent: GPTBot`. If no specific entry exists, inherits directives from `User-agent: *`. Does not execute client-side JavaScript (raw HTML and server-rendered content only).
- **Recommended Policy**: Disallow if proprietary or copyrighted training use is prohibited; allow if maximum AI discoverability is desired.

### 2. OAI-SearchBot
- **Operator**: OpenAI
- **User-Agent Token**: `OAI-SearchBot`
- **Example User-Agent String**: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)`
- **Purpose**: Indexes web content exclusively to power search results and citations inside ChatGPT Search and SearchGPT. Data gathered by OAI-SearchBot is **not** used for model training.
- **Robots.txt Behavior**: Respects `User-agent: OAI-SearchBot`. Publishers can allow `OAI-SearchBot` to gain search citations while simultaneously disallowing `GPTBot` to block model training.
- **Recommended Policy**: Allow on all public informational, product, and canonical brand pages.

### 3. ChatGPT-User
- **Operator**: OpenAI
- **User-Agent Token**: `ChatGPT-User`
- **Example User-Agent String**: `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0; +https://openai.com/bot)`
- **Purpose**: Real-time browsing agent executed when an end-user explicitly prompts ChatGPT to inspect, summarize, or verify a specific URL or recent event.
- **Robots.txt Behavior**: Respects `User-agent: ChatGPT-User` and fallback `User-agent: *`. If blocked, ChatGPT informs the user that the site cannot be reached due to robots.txt restrictions.
- **Recommended Policy**: Allow so users can interact with your brand's links directly in chat interfaces.

### 4. PerplexityBot
- **Operator**: Perplexity AI
- **User-Agent Token**: `PerplexityBot`
- **Example User-Agent String**: `Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)`
- **Purpose**: General web crawler that indexes web content for Perplexity's conversational answer engine. Extracted facts and links are displayed directly as source citations.
- **Robots.txt Behavior**: Respects `User-agent: PerplexityBot` and wildcard `*`.
- **Recommended Policy**: Allow to maximize citation frequency and entity discovery in Perplexity answers.

### 5. Perplexity-User
- **Operator**: Perplexity AI
- **User-Agent Token**: `Perplexity-User`
- **Example User-Agent String**: `Perplexity-User/1.0`
- **Purpose**: Triggered on-demand when a user query requires real-time factual synthesis or deep search over specific destination domains.
- **Robots.txt Behavior**: Respects `User-agent: Perplexity-User` directives.
- **Recommended Policy**: Allow to ensure real-time answers resolve with direct attribution.

### 6. ClaudeBot
- **Operator**: Anthropic
- **User-Agent Token**: `ClaudeBot`
- **Example User-Agent String**: `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)`
- **Purpose**: Primary web crawler for Anthropic. Gathers web text to train and improve the Claude model family.
- **Robots.txt Behavior**: Respects `User-agent: ClaudeBot`. Follows standard RFC 9309 rules.
- **Recommended Policy**: Allow if content is public domain/promotional; disallow if you restrict training access.

### 7. anthropic-ai
- **Operator**: Anthropic
- **User-Agent Token**: `anthropic-ai`
- **Example User-Agent String**: `anthropic-ai`
- **Purpose**: Legacy and auxiliary crawler token used by Anthropic for training corpus collection.
- **Robots.txt Behavior**: Respects `User-agent: anthropic-ai`. Often grouped together with `ClaudeBot` in robots.txt configurations.
- **Recommended Policy**: Mirror policy set for `ClaudeBot`.

### 8. Claude-Web
- **Operator**: Anthropic
- **User-Agent Token**: `Claude-Web`
- **Example User-Agent String**: `Mozilla/5.0 (compatible; Claude-Web/1.0; +https://www.anthropic.com)`
- **Purpose**: Live retrieval agent dispatched when Claude processes prompt-level web browsing requests.
- **Robots.txt Behavior**: Respects `User-agent: Claude-Web` and fallback `*`.
- **Recommended Policy**: Allow for real-time brand answers and link summaries.

### 9. Google-Extended
- **Operator**: Google
- **User-Agent Token**: `Google-Extended`
- **Purpose**: Standalone control token allowing site administrators to permit or disallow Google from using web content to train Gemini foundation models and Vertex AI generative APIs.
- **Robots.txt Behavior**: Disallowing `Google-Extended` **does not** impact a site's visibility, indexing, or ranking in standard Google Search (which is governed exclusively by `Googlebot`).
- **Recommended Policy**: Configure based on organizational AI training data policy.

### 10. CCBot
- **Operator**: Common Crawl Foundation
- **User-Agent Token**: `CCBot`
- **Example User-Agent String**: `CCBot/2.0 (https://commoncrawl.org/faq/)`
- **Purpose**: Crawls the open web to construct periodic publicly available web archives. These archives serve as foundational pre-training datasets for open-weight models (e.g., LLaMA, Mistral, Falcon) and research institutions.
- **Robots.txt Behavior**: Strictly complies with robots.txt, respects `Crawl-delay`, and honors wildcard `*`.
- **Recommended Policy**: Allow if you want wide distribution in academic and open-source model ecosystems.

### 11. Bytespider
- **Operator**: ByteDance
- **User-Agent Token**: `Bytespider`
- **Example User-Agent String**: `Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)`
- **Purpose**: Collects web data to power ByteDance's generative AI models, Douyin, TikTok search, and content recommendation systems.
- **Robots.txt Behavior**: Respects `User-agent: Bytespider`. Known for aggressive crawl speed; if server load is high, pair with rate-limiting or specific Disallow paths.
- **Recommended Policy**: Allow key canonical paths if ByteDance/TikTok search presence is relevant.

### 12. Applebot-Extended
- **Operator**: Apple
- **User-Agent Token**: `Applebot-Extended`
- **Purpose**: Dedicated token that enables site owners to opt out of having their web content used to train Apple's foundation models (including Apple Intelligence features).
- **Robots.txt Behavior**: Disallowing `Applebot-Extended` does not remove the site from Applebot (which powers Siri Suggestions and Spotlight web search).
- **Recommended Policy**: Allow for Apple Intelligence ecosystem integration.

### 13. meta-externalagent
- **Operator**: Meta (Facebook)
- **User-Agent Token**: `meta-externalagent`
- **Example User-Agent String**: `Mozilla/5.0 (compatible; meta-externalagent/1.1; +https://developers.facebook.com/docs/sharing/webmasters/crawler)`
- **Purpose**: Dispatched to collect public web data for training Meta's Llama models, improving Meta AI assistant responses, and indexing content shared across Meta platforms.
- **Robots.txt Behavior**: Respects `User-agent: meta-externalagent` and `*`.
- **Recommended Policy**: Allow for discoverability within Meta AI search and assistant products.

### 14. cohere-ai
- **Operator**: Cohere
- **User-Agent Token**: `cohere-ai`
- **Example User-Agent String**: `cohere-ai`
- **Purpose**: Crawls public web pages to build training sets for Cohere's enterprise LLMs, multilingual embeddings, and reranking models.
- **Robots.txt Behavior**: Respects `User-agent: cohere-ai` and `*`.
- **Recommended Policy**: Allow for presence in enterprise RAG systems leveraging Cohere models.

### 15. Omgilibot
- **Operator**: Webz.io
- **User-Agent Token**: `Omgilibot`
- **Example User-Agent String**: `Omgilibot/0.4 (+http://www.omgili.com/Crawler.html)`
- **Purpose**: Crawls discussion boards, news, and public web content to provide structured data feeds to commercial AI and analytics platforms.
- **Robots.txt Behavior**: Respects `User-agent: Omgilibot` and wildcard `*`.
- **Recommended Policy**: Configure based on organizational policy for commercial training feeds.

### 16. Googlebot
- **Operator**: Google
- **User-Agent Token**: `Googlebot`
- **Example User-Agent String**: `Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)`
- **Purpose**: Google's primary web crawler. Included in registry as a baseline search indexer reference to compare AI-specific restrictions against general search indexing access.
- **Robots.txt Behavior**: Respects `User-agent: Googlebot` and wildcard `*`. Executes client-side JavaScript.
- **Recommended Policy**: Allow on all public indexable pages.

---

## robots.txt Matching Rules

### RFC 9309 Parser Compliance
1. **Case-Insensitive User-Agent Matching**:
   Per RFC 9309 Section 2.2.1, user-agent tokens are matched case-insensitively. A rule written as `User-agent: gptbot` matches `GPTBot`, `gptbot`, and `GPTBOT`.
2. **Wildcard Fallback (`User-agent: *`)**:
   If no record explicitly names a crawler's token (e.g., `User-agent: GPTBot`), the crawler follows the rules defined under `User-agent: *`.
3. **HTTP 404 & Connection Errors**:
   Under RFC 9309 Section 2.3.1.2, if `robots.txt` returns an HTTP 404 (Not Found) or a connection error, all crawlers are allowed full access to the site.
4. **Cloudflare & Bot-Wall Challenges**:
   If automated security firewalls (Cloudflare, Akamai, DataDome) return HTTP 403 or 503 challenges to automated user-agents, the crawlers cannot retrieve `robots.txt` or page HTML, causing silent exclusion from AI citation indexes.

---

## Example Config: Allow Search Bots While Restricting Training Bots

```txt
# Allow search & live retrieval crawlers
User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Claude-Web
Allow: /

# Restrict foundation model training crawlers
User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: Applebot-Extended
Disallow: /

# Default policy for all other crawlers
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /private/

Sitemap: https://example.com/sitemap.xml
```
