from __future__ import annotations

from urllib.parse import urljoin

import httpx

from jobinator.discovery.errors import SourceFetchError
from jobinator.discovery.link_sources import identify_discovery_link_source


async def fetch_reachable_source(
    client: httpx.AsyncClient,
    url: str,
    *,
    source_label: str,
    posting_label: str,
) -> httpx.Response:
    try:
        current_url = url
        for _ in range(6):
            response = await client.get(current_url, follow_redirects=False)
            if not response.is_redirect or "location" not in response.headers:
                break
            redirected_url = urljoin(current_url, response.headers["location"])
            if identify_discovery_link_source(redirected_url) == "linkedin":
                raise SourceFetchError(
                    f"{source_label} redirected to LinkedIn; automated LinkedIn "
                    "browsing was not attempted."
                )
            current_url = redirected_url
        else:
            raise SourceFetchError(f"{source_label} exceeded the redirect limit.")
    except httpx.HTTPError as error:
        raise SourceFetchError(
            f"{source_label} request failed ({type(error).__name__})."
        ) from error
    if response.status_code in {404, 410}:
        raise SourceFetchError(
            f"{posting_label} was not found (HTTP {response.status_code})."
        )
    if response.status_code in {401, 403, 429}:
        raise SourceFetchError(
            f"{source_label} blocked access (HTTP {response.status_code}). "
            "Browser automation was not attempted."
        )
    try:
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SourceFetchError(
            f"{source_label} request failed (HTTP {response.status_code})."
        ) from error
    return response
