import pytest
import check_access


REQUIRED_CRAWLERS = [
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "PerplexityBot",
    "Perplexity-User",
    "ClaudeBot",
    "anthropic-ai",
    "Claude-Web",
    "Google-Extended",
    "CCBot",
    "Bytespider",
    "Applebot-Extended",
    "meta-externalagent",
    "cohere-ai",
]


def test_crawler_registry_contains_minimum_crawlers():
    """Assert that AI_CRAWLERS in check_access.py contains all minimum required AI user-agents."""
    assert hasattr(check_access, "AI_CRAWLERS"), "check_access must define AI_CRAWLERS"

    registered_agents = [agent for agent, _ in check_access.AI_CRAWLERS]

    missing = [c for c in REQUIRED_CRAWLERS if c not in registered_agents]
    assert not missing, f"check_access.AI_CRAWLERS is missing required crawlers: {missing}"


@pytest.mark.parametrize("crawler", REQUIRED_CRAWLERS)
def test_each_required_crawler_present(crawler: str):
    """Individually assert each expected AI crawler is present in the registry."""
    registered_agents = [agent for agent, _ in check_access.AI_CRAWLERS]
    assert crawler in registered_agents, f"Crawler '{crawler}' not found in check_access.AI_CRAWLERS"
