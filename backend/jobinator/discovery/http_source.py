from __future__ import annotations

import httpx

from jobinator.discovery.errors import SourceFetchError


async def fetch_reachable_source(
    client: httpx.AsyncClient,
    url: str,
    *,
    source_label: str,
    posting_label: str,
) -> httpx.Response:
    try:
        response = await client.get(url)
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
