from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DiscoveryLinkSourceDefinition:
    id: str
    label: str
    domains: tuple[str, ...]


DISCOVERY_LINK_SOURCES = (
    DiscoveryLinkSourceDefinition("linkedin", "LinkedIn", ("linkedin.com",)),
    DiscoveryLinkSourceDefinition("wellfound", "Wellfound", ("wellfound.com",)),
    DiscoveryLinkSourceDefinition(
        "yc-work-at-a-startup",
        "YC Work at a Startup",
        ("workatastartup.com",),
    ),
    DiscoveryLinkSourceDefinition("builtin", "Built In", ("builtin.com",)),
    DiscoveryLinkSourceDefinition(
        "welcome-to-the-jungle",
        "Welcome to the Jungle",
        ("welcometothejungle.com", "otta.com"),
    ),
    DiscoveryLinkSourceDefinition("simplify", "Simplify", ("simplify.jobs",)),
    DiscoveryLinkSourceDefinition(
        "engineering-list",
        "Engineering-specific list",
        (),
    ),
)
DISCOVERY_LINK_SOURCE_IDS = frozenset(source.id for source in DISCOVERY_LINK_SOURCES)


def identify_discovery_link_source(url: str) -> str:
    hostname = (urlsplit(url).hostname or "").lower()
    for source in DISCOVERY_LINK_SOURCES:
        if any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in source.domains
        ):
            return source.id
    return "engineering-list"
