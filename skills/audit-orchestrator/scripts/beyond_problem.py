#!/usr/bin/env python3
"""
skills/audit-orchestrator/scripts/beyond_problem.py

Generates proactive, forward-looking recommendations tied to Round-2 concepts:
1. Entity corroboration across independent sources (Wikipedia, Crunchbase, LinkedIn, Wikidata) via sameAs (Appendix D/B)
2. Canonical facts page (/facts or /about with one unambiguous plain-text sentence per key fact) (Appendix C)
3. Conversational FAQ (question-shaped headings matching user prompts) (Appendix B)
4. Locale/language variants (hreflang + locale-specific schema) (Appendix E)
5. Email-summary resilience (TL;DR text blocks at top of transactional emails) (Appendix F)
6. Sitemap freshness signal (<lastmod> in sitemap.xml) (Appendix A)
"""

from typing import Optional


ROUND_2_SUGGESTIONS = [
    {
        "title": "Cross-link verified entity profiles across independent authority platforms via sameAs",
        "rationale": "Independent corroboration across Wikipedia, Crunchbase, LinkedIn, and Wikidata validates brand legitimacy and feeds entity resolution algorithms in knowledge graph construction (Appendix D/B).",
        "mechanism": "LLM knowledge engines construct high-confidence entity nodes by resolving bidirectional sameAs references across independent high-authority knowledge bases.",
        "priority": "high",
    },
    {
        "title": "Publish a canonical facts page with unambiguous declarative plain-text assertions",
        "rationale": "A dedicated /facts or /about page presenting one unambiguous plain-text sentence per core attribute (founding date, headquarters, leadership, core products) eliminates extraction ambiguity for LLM crawlers (Appendix C).",
        "mechanism": "Declarative single-fact sentences minimize semantic parsing entropy during retrieval-augmented generation (RAG) and prevent hallucinated brand claims.",
        "priority": "high",
    },
    {
        "title": "Structure conversational FAQ sections with question-shaped headings matching user prompts",
        "rationale": "Formulating headings as explicit natural-language questions directly mirrors user prompt patterns submitted to AI search engines (Appendix B).",
        "mechanism": "Question-formatted headings maximize semantic vector cosine similarity against conversational user queries, triggering direct answer citations.",
        "priority": "medium",
    },
    {
        "title": "Implement hreflang annotations and locale-specific schema for regional disambiguation",
        "rationale": "Explicit hreflang link tags and localized schema markup distinguish regional product lines, currencies, and language variations for global AI assistants (Appendix E).",
        "mechanism": "Locale and alternate tags prevent search bots from conflating regional entities or surfacing incorrect currency and availability in localized AI answers.",
        "priority": "medium",
    },
    {
        "title": "Embed machine-readable TL;DR summary blocks at the top of transactional emails",
        "rationale": "AI email summarizers (e.g., Apple Intelligence, Gemini in Gmail, Copilot) generate automatic summaries based on early email tokens, requiring key details upfront (Appendix F).",
        "mechanism": "Structured key-value summary blocks at the beginning of email HTML ensure client-side AI summarizers extract order numbers, dates, and actions without truncation errors.",
        "priority": "low",
    },
    {
        "title": "Maintain accurate <lastmod> timestamps in sitemap.xml to signal content freshness",
        "rationale": "Including precise, genuine <lastmod> dates in sitemap.xml enables AI crawlers with limited crawl budgets to discover and ingest fresh updates promptly (Appendix A).",
        "mechanism": "AI search engines prioritize re-crawling URLs with recent sitemap <lastmod> timestamps, keeping their retrieval indexes and vector embeddings synchronized.",
        "priority": "medium",
    },
]


def get_beyond_problem_suggestions(url: str = "", findings: Optional[list] = None) -> list[dict]:
    """
    Return proactive beyond-problem suggestions tied to Round-2 concepts.
    Always returns at least 6 validated suggestions.
    """
    # Return a deep-copied list of the canonical suggestions
    return [dict(item) for item in ROUND_2_SUGGESTIONS]


# Alias for backward compatibility
generate_beyond_problem_suggestions = get_beyond_problem_suggestions
