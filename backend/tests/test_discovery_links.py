from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from jobinator.config import Settings
from jobinator.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
DISCOVERY_URL = "https://wellfound.com/jobs/12345-junior-software-engineer"
OFFICIAL_URL = "https://careers.acme.example/jobs/junior-software-engineer"
WORKDAY_URL = (
    "https://acme.wd5.myworkdayjobs.com/en-US/Acme_Careers/job/Chicago-IL/"
    "Junior-Platform-Engineer_JR-000123"
)
WORKDAY_API_URL = (
    "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/job/"
    "Chicago-IL/Junior-Platform-Engineer_JR-000123"
)


def load_discovery_links_fixture() -> dict[str, list[dict[str, str]]]:
    fixture_path = Path(__file__).parent / "fixtures" / "discovery_links.json"
    return cast(dict[str, list[dict[str, str]]], json.loads(fixture_path.read_text()))


def load_discovery_link_failures() -> dict[str, dict[str, Any]]:
    fixture_path = FIXTURES / "discovery_link_failures.json"
    return cast(dict[str, dict[str, Any]], json.loads(fixture_path.read_text()))


@pytest.mark.anyio
async def test_linkedin_discovery_link_is_preserved_for_manual_review_without_browsing(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []

    def source_response(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        raise AssertionError("LinkedIn must not be browsed during discovery-link intake.")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )
    linkedin_url = "https://www.linkedin.com/jobs/view/987654321"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intake = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": linkedin_url}]},
        )
        listed = await client.get("/api/discovery/links")

    await source_client.aclose()
    expected_link = {
        "id": 1,
        "url": linkedin_url,
        "source_platform": "linkedin",
        "status": "unresolved",
        "resolved_url": None,
        "snapshot_id": None,
        "reason": (
            "LinkedIn links are preserved for manual review; automated LinkedIn "
            "browsing was not attempted."
        ),
        "created_at": "2026-08-05T12:00:00Z",
    }
    assert intake.status_code == 200
    assert intake.json() == {"discovered": 0, "links": [expected_link]}
    assert listed.status_code == 200
    assert listed.json() == [expected_link]
    assert requested_urls == []


@pytest.mark.anyio
async def test_source_override_cannot_enable_automated_linkedin_browsing(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []
    linkedin_url = "https://www.linkedin.com/jobs/view/987654321"

    def source_response(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200)

    source_client = httpx.AsyncClient(
        transport=httpx.MockTransport(source_response)
    )
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/discovery/links",
            json={
                "links": [
                    {
                        "url": linkedin_url,
                        "source_platform": "engineering-list",
                    }
                ]
            },
        )

    await source_client.aclose()
    assert response.json()["links"][0]["status"] == "unresolved"
    assert "automated LinkedIn browsing was not attempted" in response.json()["links"][0][
        "reason"
    ]
    assert requested_urls == []


@pytest.mark.anyio
async def test_redirect_to_linkedin_is_preserved_without_following_it(
    tmp_path: Path,
) -> None:
    wrapper_url = "https://engineering.example/jobs/linkedin-wrapper"
    linkedin_url = "https://www.linkedin.com/jobs/view/987654321"
    requested_urls: list[str] = []

    def source_response(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == wrapper_url:
            return httpx.Response(302, headers={"Location": linkedin_url})
        raise AssertionError("The LinkedIn redirect must not be followed.")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": wrapper_url}]},
        )

    await source_client.aclose()
    assert response.json()["links"][0]["status"] == "unresolved"
    assert "redirected to LinkedIn" in response.json()["links"][0]["reason"]
    assert requested_urls == [wrapper_url]


@pytest.mark.anyio
async def test_one_intake_identifies_named_sources_and_accepts_a_confirmed_source(
    tmp_path: Path,
) -> None:
    fixture = load_discovery_links_fixture()
    requested_urls: list[str] = []

    def blocked_source(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(403)

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(blocked_source))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )
    submissions = [
        {
            key: value
            for key, value in link.items()
            if key in {"url", "source_platform"}
        }
        for link in fixture["links"]
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/discovery/links", json={"links": submissions})
        source_definitions = await client.get("/api/discovery/link-sources")

    await source_client.aclose()
    assert response.status_code == 200
    links = response.json()["links"]
    assert [link["source_platform"] for link in links] == [
        link["expected_platform"] for link in fixture["links"]
    ]
    assert all(link["status"] == "unresolved" for link in links)
    assert all(
        link["reason"].endswith("Open the source link for manual review.")
        for link in links[1:]
    )
    assert requested_urls == [link["url"] for link in fixture["links"][1:]]
    assert [source["id"] for source in source_definitions.json()] == [
        "linkedin",
        "wellfound",
        "yc-work-at-a-startup",
        "builtin",
        "welcome-to-the-jungle",
        "simplify",
        "engineering-list",
    ]


@pytest.mark.anyio
async def test_reachable_discovery_link_resolves_and_normalizes_an_official_posting(
    tmp_path: Path,
) -> None:
    discovery_html = (FIXTURES / "discovery_source_listing.html").read_text()
    official_html = (FIXTURES / "company_career_posting.html").read_text()

    def source_response(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DISCOVERY_URL:
            return httpx.Response(200, text=discovery_html)
        if str(request.url) == OFFICIAL_URL:
            return httpx.Response(200, text=official_html)
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intake = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": DISCOVERY_URL}]},
        )
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    link = intake.json()["links"][0]
    assert intake.json()["discovered"] == 1
    assert link["status"] == "resolved"
    assert link["resolved_url"] == OFFICIAL_URL
    assert link["snapshot_id"] == 1
    assert link["reason"] is None
    opportunities = discovered.json()
    assert len(opportunities) == 1
    assert opportunities[0]["source_url"] == DISCOVERY_URL
    assert opportunities[0]["source_platform"] == "wellfound"
    assert opportunities[0]["canonical_url"] == OFFICIAL_URL
    assert opportunities[0]["company"] == "Acme Corp"
    assert opportunities[0]["title"] == "Junior Software Engineer"
    assert opportunities[0]["location"] == "New York, NY"
    assert opportunities[0]["detected_requirements"] == [
        "Experience with Python",
        "Clear written communication",
    ]
    assert opportunities[0]["raw_posting"]["_discovery"] == {
        "source_platform": "wellfound",
        "source_url": DISCOVERY_URL,
    }


@pytest.mark.anyio
async def test_official_company_posting_can_use_an_openings_path(
    tmp_path: Path,
) -> None:
    openings_url = "https://acme.example/openings/123"
    discovery_html = (
        '<a href="/jobs/another-role">Related job</a>'
        '<a href="https://www.linkedin.com/company/acme">Acme on LinkedIn</a>'
        f'<a href="{openings_url}">View at Acme</a>'
    )
    official_html = (FIXTURES / "company_career_posting.html").read_text()
    requested_urls: list[str] = []

    def source_response(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == DISCOVERY_URL:
            return httpx.Response(200, text=discovery_html)
        if str(request.url) == openings_url:
            return httpx.Response(200, text=official_html)
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": DISCOVERY_URL}]},
        )

    await source_client.aclose()
    assert response.json()["discovered"] == 1
    assert response.json()["links"][0]["resolved_url"] == OFFICIAL_URL
    assert requested_urls == [DISCOVERY_URL, openings_url]


@pytest.mark.anyio
async def test_reachable_listing_details_normalize_without_following_another_page(
    tmp_path: Path,
) -> None:
    builtin_url = "https://builtin.com/job/software-engineering/junior-engineer/111"
    listing_html = (FIXTURES / "company_career_posting.html").read_text()
    requested_urls: list[str] = []

    def source_response(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, text=listing_html)

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intake = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": builtin_url}]},
        )
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert intake.json()["discovered"] == 1
    assert intake.json()["links"][0]["resolved_url"] == OFFICIAL_URL
    assert discovered.json()[0]["source_platform"] == "builtin"
    assert requested_urls == [builtin_url]


@pytest.mark.anyio
async def test_discovery_link_can_resolve_to_a_reachable_ats_posting(
    tmp_path: Path,
) -> None:
    simplify_url = "https://simplify.jobs/p/abcd1234/Junior-Platform-Engineer"
    discovery_html = (FIXTURES / "discovery_source_listing.html").read_text().replace(
        OFFICIAL_URL,
        WORKDAY_URL,
    )
    workday_payload = json.loads((FIXTURES / "workday_posting.json").read_text())

    def source_response(request: httpx.Request) -> httpx.Response:
        if str(request.url) == simplify_url:
            return httpx.Response(200, text=discovery_html)
        if str(request.url) == WORKDAY_API_URL:
            return httpx.Response(200, json=workday_payload)
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intake = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": simplify_url}]},
        )
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert intake.json()["discovered"] == 1
    assert intake.json()["links"][0]["resolved_url"] == WORKDAY_URL
    assert discovered.json()[0]["source_platform"] == "simplify"
    assert discovered.json()[0]["ats_posting_id"] == "JR-000123"


@pytest.mark.anyio
async def test_resolution_follows_redirects_and_prefers_ranked_ats_link(
    tmp_path: Path,
) -> None:
    redirected_url = f"{DISCOVERY_URL}?ref=curated"
    lever_url = "https://jobs.lever.co/acme/lever-123"
    lever_api_url = "https://api.lever.co/v0/postings/acme?mode=json"
    aggregator_posting = (FIXTURES / "company_career_posting.html").read_text().replace(
        OFFICIAL_URL,
        DISCOVERY_URL,
    )
    discovery_html = aggregator_posting.replace(
        "</body>",
        (
            '<a href="https://social.example/acme">Follow Acme</a>'
            f'<a href="{lever_url}">Apply on company ATS</a>'
            "</body>"
        ),
    )
    lever_fixture = cast(
        dict[str, list[dict[str, Any]]],
        json.loads((FIXTURES / "lever_postings.json").read_text()),
    )
    requested_urls: list[str] = []

    def source_response(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == DISCOVERY_URL:
            return httpx.Response(302, headers={"Location": redirected_url})
        if str(request.url) == redirected_url:
            return httpx.Response(200, text=discovery_html)
        if str(request.url) == lever_api_url:
            return httpx.Response(200, json=lever_fixture["postings"])
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intake = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": DISCOVERY_URL}]},
        )
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert intake.json()["links"][0]["resolved_url"] == lever_url
    assert discovered.json()[0]["canonical_url"] == lever_url
    assert discovered.json()[0]["source_platform"] == "wellfound"
    assert requested_urls == [DISCOVERY_URL, redirected_url, lever_api_url]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("discovery_url", "source_platform", "official_url", "api_url", "fixture_name"),
    [
        (
            "https://wellfound.com/jobs/greenhouse-role",
            "wellfound",
            "https://boards.greenhouse.io/acme/jobs/12345",
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
            "greenhouse_jobs.json",
        ),
        (
            "https://builtin.com/job/software-engineering/ashby-role/222",
            "builtin",
            "https://jobs.ashbyhq.com/acme/ashby-456",
            "https://api.ashbyhq.com/posting-api/job-board/acme",
            "ashby_postings.json",
        ),
    ],
)
async def test_discovery_links_resolve_greenhouse_and_ashby_destinations(
    tmp_path: Path,
    discovery_url: str,
    source_platform: str,
    official_url: str,
    api_url: str,
    fixture_name: str,
) -> None:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    discovery_html = (
        '<a href="https://social.example/acme">Follow Acme</a>'
        f'<a href="{official_url}">Apply on ATS</a>'
    )

    def source_response(request: httpx.Request) -> httpx.Response:
        if str(request.url) == discovery_url:
            return httpx.Response(200, text=discovery_html)
        if str(request.url) == api_url:
            return httpx.Response(200, json=payload)
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / f'{source_platform}.db'}",
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        intake = await client.post(
            "/api/discovery/links",
            json={"links": [{"url": discovery_url}]},
        )
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert intake.json()["discovered"] == 1
    assert intake.json()["links"][0]["resolved_url"] == official_url
    assert discovered.json()[0]["source_platform"] == source_platform


@pytest.mark.anyio
async def test_resolved_discovery_snapshot_merges_with_the_official_source_snapshot(
    tmp_path: Path,
) -> None:
    discovery_html = (FIXTURES / "discovery_source_listing.html").read_text()
    official_html = (FIXTURES / "company_career_posting.html").read_text()

    def source_response(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DISCOVERY_URL:
            return httpx.Response(200, text=discovery_html)
        if str(request.url) == OFFICIAL_URL:
            return httpx.Response(200, text=official_html)
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(career_page_urls=[OFFICIAL_URL]),
        source_client=source_client,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/discovery/ingest")
        await client.post(
            "/api/discovery/links",
            json={"links": [{"url": DISCOVERY_URL}]},
        )
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    opportunities = discovered.json()
    assert len(opportunities) == 1
    assert opportunities[0]["preferred_apply_url"] == OFFICIAL_URL
    assert {snapshot["source_platform"] for snapshot in opportunities[0]["snapshots"]} == {
        "company",
        "wellfound",
    }


@pytest.mark.anyio
async def test_blocked_and_expired_links_remain_visible_with_manual_review_reasons(
    tmp_path: Path,
) -> None:
    failures = load_discovery_link_failures()
    statuses = {
        failure["url"]: failure["status_code"]
        for failure in failures.values()
    }

    def source_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(statuses[str(request.url)])

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/discovery/links",
            json={
                "links": [
                    {"url": failure["url"]}
                    for failure in failures.values()
                ]
            },
        )
        listed = await client.get("/api/discovery/links")

    await source_client.aclose()
    links_by_url = {link["url"]: link for link in listed.json()}
    for failure in failures.values():
        link = links_by_url[failure["url"]]
        assert link["status"] == "unresolved"
        assert link["reason"] == failure["expected_reason"]
        assert link["resolved_url"] is None
