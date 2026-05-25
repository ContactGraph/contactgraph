"""Fetch recent public posts from Bluesky and GitHub after handle discovery."""

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlparse

import httpx

from contactsafe_server.config import Settings

_BSKY_PROFILE_RE: re.Pattern[str] = re.compile(
    r"https?://(?:www\.)?bsky\.app/profile/([A-Za-z0-9._-]+)",
    flags=re.IGNORECASE,
)
_GITHUB_PROFILE_RE: re.Pattern[str] = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9-]+)(?:/|$)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PlatformPost:
    platform: str
    text: str
    url: str
    created_at: str | None = None


class PlatformActivityClient:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings
        self._timeout: float = settings.platform_activity_timeout_seconds

    async def fetch_recent_posts(
        self,
        *,
        social_profiles: dict[str, str],
        max_posts_per_platform: int | None = None,
    ) -> list[PlatformPost]:
        limit: int = max_posts_per_platform or self._settings.platform_activity_max_posts
        posts: list[PlatformPost] = []

        bluesky_url: str | None = social_profiles.get("bluesky")
        if bluesky_url:
            handle: str | None = _extract_bluesky_handle(bluesky_url)
            if handle:
                posts.extend(await self._fetch_bluesky_posts(handle, limit=limit))

        github_url: str | None = social_profiles.get("github")
        if github_url:
            login: str | None = _extract_github_login(github_url)
            if login:
                posts.extend(await self._fetch_github_activity(login, limit=limit))

        return posts

    async def _fetch_bluesky_posts(self, handle: str, *, limit: int) -> list[PlatformPost]:
        url: str = (
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
            f"?actor={handle}&limit={limit}&filter=posts_no_replies"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.get(url)
                response.raise_for_status()
                data: dict[str, object] = cast(dict[str, object], response.json())
        except Exception:
            return []

        feed_raw: object = data.get("feed")
        if not isinstance(feed_raw, list):
            return []

        posts: list[PlatformPost] = []
        for item_raw in cast(list[object], feed_raw):
            if not isinstance(item_raw, dict):
                continue
            item: dict[str, object] = cast(dict[str, object], item_raw)
            post_raw: object = item.get("post")
            if not isinstance(post_raw, dict):
                continue
            post: dict[str, object] = cast(dict[str, object], post_raw)
            record_raw: object = post.get("record")
            if not isinstance(record_raw, dict):
                continue
            record: dict[str, object] = cast(dict[str, object], record_raw)
            text_raw: object = record.get("text")
            if not isinstance(text_raw, str) or not text_raw.strip():
                continue
            uri_raw: object = post.get("uri")
            created_raw: object = record.get("createdAt")
            posts.append(
                PlatformPost(
                    platform="bluesky",
                    text=text_raw.strip(),
                    url=_bluesky_post_url(uri_raw, handle),
                    created_at=created_raw if isinstance(created_raw, str) else None,
                )
            )
        return posts

    async def _fetch_github_activity(self, login: str, *, limit: int) -> list[PlatformPost]:
        url: str = f"https://api.github.com/users/{login}/events/public?per_page={limit}"
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.get(url, headers=headers)
                response.raise_for_status()
                events_raw: object = response.json()
        except Exception:
            return []

        if not isinstance(events_raw, list):
            return []

        posts: list[PlatformPost] = []
        for event_raw in cast(list[object], events_raw):
            if not isinstance(event_raw, dict):
                continue
            event: dict[str, object] = cast(dict[str, object], event_raw)
            event_type_raw: object = event.get("type")
            event_type: str = event_type_raw if isinstance(event_type_raw, str) else "Event"
            repo_raw: object = event.get("repo")
            repo_name: str = ""
            if isinstance(repo_raw, dict):
                repo: dict[str, object] = cast(dict[str, object], repo_raw)
                name_raw: object = repo.get("name")
                repo_name = name_raw if isinstance(name_raw, str) else ""
            created_raw: object = event.get("created_at")
            text: str = f"{event_type}: {repo_name}".strip(": ")
            if not text:
                continue
            posts.append(
                PlatformPost(
                    platform="github",
                    text=text,
                    url=f"https://github.com/{login}",
                    created_at=created_raw if isinstance(created_raw, str) else None,
                )
            )
        return posts


def extract_handles_from_urls(urls: list[str]) -> dict[str, str]:
    profiles: dict[str, str] = {}
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        host: str = (parsed.hostname or "").lower().removeprefix("www.")
        if host == "bsky.app" and "bluesky" not in profiles:
            profiles["bluesky"] = url
        elif host == "github.com" and "github" not in profiles:
            profiles["github"] = url
    return profiles


def posts_to_activity_blob(posts: list[PlatformPost]) -> str:
    parts: list[str] = []
    for post in posts:
        prefix: str = f"[{post.platform}]"
        parts.append(f"{prefix} {post.text}")
    return "\n".join(parts)


def _extract_bluesky_handle(url: str) -> str | None:
    match: re.Match[str] | None = _BSKY_PROFILE_RE.search(url)
    if match is not None:
        return match.group(1)
    parsed = urlparse(url)
    if (parsed.hostname or "").endswith("bsky.app"):
        path_parts: list[str] = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "profile":
            return path_parts[1]
    return None


def _extract_github_login(url: str) -> str | None:
    match: re.Match[str] | None = _GITHUB_PROFILE_RE.search(url)
    if match is not None:
        login: str = match.group(1)
        if login.lower() not in {"orgs", "organizations", "settings", "marketplace"}:
            return login
    return None


def _bluesky_post_url(uri_raw: object, handle: str) -> str:
    if isinstance(uri_raw, str) and "app.bsky.feed.post/" in uri_raw:
        post_id: str = uri_raw.rsplit("/", 1)[-1]
        return f"https://bsky.app/profile/{handle}/post/{post_id}"
    return f"https://bsky.app/profile/{handle}"
