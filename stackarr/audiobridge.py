"""Direct Libraseer -> Shelfmark-TorBox audiobook acquisition.

The historical module name is retained so existing Stackarr-derived call sites
do not need invasive changes. There is no bridge service.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

log = logging.getLogger("stackarr.audiobridge")
_SEARCH_TIMEOUT = 180
_API_TIMEOUT = 30
_AUDIO_FORMATS = {"mp3", "m4b", "m4a", "aac", "flac", "ogg", "opus", "zip", "rar", "7z"}


class AudiobookShelfmarkError(RuntimeError):
    pass


def url() -> str:
    return os.environ.get("SHELFMARK_AUDIOBOOK_URL", "").rstrip("/")


def username() -> str:
    return os.environ.get("SHELFMARK_AUDIOBOOK_USERNAME", "")


def password() -> str:
    return os.environ.get("SHELFMARK_AUDIOBOOK_PASSWORD", "")


def source() -> str:
    return (os.environ.get("SHELFMARK_AUDIOBOOK_SOURCE", "audiobookbay").strip().lower()
            or "audiobookbay")


def configured() -> bool:
    return bool(url())


def _session() -> requests.Session:
    if not configured():
        raise AudiobookShelfmarkError("Shelfmark-TorBox audiobook URL is not configured.")

    user = username().strip()
    secret = password()
    if bool(user) != bool(secret):
        raise AudiobookShelfmarkError(
            "Shelfmark-TorBox authentication is incomplete: set both username and password."
        )

    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    if not user:
        return s

    try:
        r = s.post(
            f"{url()}/api/auth/login",
            json={"username": user, "password": secret, "remember_me": True},
            timeout=_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AudiobookShelfmarkError(f"Could not reach Shelfmark-TorBox login: {exc}") from exc

    if r.status_code in (401, 403):
        raise AudiobookShelfmarkError("Shelfmark-TorBox rejected the configured username/password.")
    if r.status_code == 429:
        raise AudiobookShelfmarkError("Shelfmark-TorBox login is temporarily rate-limited.")
    if not r.ok:
        raise AudiobookShelfmarkError(f"Shelfmark-TorBox login failed with HTTP {r.status_code}.")
    return s


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _format_hints(release: dict[str, Any]) -> set[str]:
    values: list[str] = []
    for key in ("format", "title"):
        value = release.get(key)
        if isinstance(value, str):
            values.append(value)
    extra = release.get("extra")
    if isinstance(extra, dict):
        for key in ("format", "formats", "formats_display", "title_raw"):
            value = extra.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value)
    return {t for t in re.split(r"[^a-z0-9]+", " ".join(values).lower()) if t}


def _score_release(release: dict[str, Any], title: str, author: str) -> int | None:
    if str(release.get("source") or "").strip().lower() != source():
        return None
    if str(release.get("protocol") or "").strip().lower() != "torrent":
        return None
    content_type = str(release.get("content_type") or "").strip().lower()
    if content_type and content_type != "audiobook":
        return None
    language = str(release.get("language") or "").strip().lower()
    if language not in ("", "en", "eng", "english"):
        return None

    release_title = str(release.get("title") or "")
    extra = release.get("extra")
    raw_title = str(extra.get("title_raw") or release_title) if isinstance(extra, dict) else release_title

    wanted = _norm(title)
    got = _norm(raw_title)
    if not wanted or wanted not in got:
        return None

    hints = _format_hints(release)
    explicit_format = str(release.get("format") or "").strip().lower()
    if explicit_format and not (hints & _AUDIO_FORMATS):
        return None

    score = 100
    if _norm(release_title) == wanted:
        score += 50
    elif _norm(release_title).startswith(wanted + " "):
        score += 25

    for word in (w for w in _norm(author).split() if len(w) >= 3):
        if word in got.split():
            score += 8

    if "m4b" in hints:
        score += 10
    elif "mp3" in hints:
        score += 6

    if any(x in got for x in ("complete series", "complete collection", "box set", "boxset", "omnibus")):
        score -= 120
    return score if score >= 0 else None


def _choose_release(releases: list[dict[str, Any]], title: str, author: str):
    ranked = []
    for idx, release in enumerate(releases):
        if not isinstance(release, dict):
            continue
        score = _score_release(release, title, author)
        if score is not None:
            ranked.append((score, -idx, release))
    if not ranked:
        return None, 0
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return ranked[0][2], len(ranked)


def _search_once(session: requests.Session, title: str, author: str) -> list[dict[str, Any]]:
    params = {
        "provider": "manual",
        "book_id": f"libraseer:{title}",
        "source": source(),
        "title": title,
        "author": author,
        "manual_query": title,
        "content_type": "audiobook",
        "expand_search": "false",
    }
    try:
        r = session.get(f"{url()}/api/releases", params=params, timeout=_SEARCH_TIMEOUT)
    except requests.RequestException as exc:
        raise AudiobookShelfmarkError(f"Audiobook release search failed: {exc}") from exc

    if r.status_code in (401, 403):
        raise AudiobookShelfmarkError("Shelfmark-TorBox rejected this session.")
    if r.status_code == 429:
        raise AudiobookShelfmarkError("Shelfmark-TorBox/AudiobookBay is rate-limited.")
    if not r.ok:
        detail = ""
        try:
            body = r.json()
            if isinstance(body, dict):
                detail = str(body.get("error") or body.get("message") or "")
        except ValueError:
            pass
        raise AudiobookShelfmarkError(
            f"Shelfmark-TorBox release search returned HTTP {r.status_code}"
            + (f": {detail}" if detail else "")
        )

    try:
        body = r.json()
    except ValueError as exc:
        raise AudiobookShelfmarkError("Shelfmark-TorBox returned invalid JSON.") from exc
    releases = body.get("releases", []) if isinstance(body, dict) else []
    if not isinstance(releases, list):
        raise AudiobookShelfmarkError("Shelfmark-TorBox returned an invalid releases list.")
    return releases


def _queue_release(session: requests.Session, release: dict[str, Any], title: str, author: str) -> str:
    payload = dict(release)
    payload["content_type"] = "audiobook"
    if not payload.get("title"):
        payload["title"] = title
    if author:
        payload["author"] = author

    try:
        r = session.post(f"{url()}/api/releases/download", json=payload, timeout=_API_TIMEOUT)
    except requests.RequestException as exc:
        raise AudiobookShelfmarkError(f"Could not queue audiobook release: {exc}") from exc

    if r.status_code in (401, 403):
        raise AudiobookShelfmarkError("Shelfmark-TorBox refused the selected release.")
    if r.status_code == 429:
        raise AudiobookShelfmarkError("Shelfmark-TorBox is rate-limited while queueing.")
    if not r.ok:
        detail = ""
        try:
            body = r.json()
            if isinstance(body, dict):
                detail = str(body.get("error") or body.get("message") or "")
        except ValueError:
            pass
        raise AudiobookShelfmarkError(
            f"Shelfmark-TorBox queue returned HTTP {r.status_code}"
            + (f": {detail}" if detail else "")
        )

    try:
        body = r.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        for key in ("task_id", "book_id", "id", "ref"):
            value = body.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return str(payload.get("source_id") or "").strip()


def _activity() -> dict[str, dict[str, Any]]:
    try:
        s = _session()
        r = s.get(f"{url()}/api/activity/snapshot", timeout=_API_TIMEOUT)
        if not r.ok:
            return {}
        body = r.json()
    except (requests.RequestException, ValueError, AudiobookShelfmarkError):
        return {}

    buckets = body.get("status") if isinstance(body, dict) else None
    if not isinstance(buckets, dict):
        return {}
    out = {}
    for state, entries in buckets.items():
        if not isinstance(entries, dict):
            continue
        for task_id, payload in entries.items():
            item = dict(payload) if isinstance(payload, dict) else {}
            item["state"] = str(state).strip().lower()
            out[str(task_id)] = item
    return out


def job_status(ref: str) -> dict | None:
    ref = (ref or "").strip()
    if not ref or not configured():
        return None
    item = _activity().get(ref)
    if not isinstance(item, dict):
        return None

    state = str(item.get("state") or "").strip().lower()
    message = str(item.get("status_message") or item.get("error") or "").strip()
    if state in {"error", "failed", "cancelled"}:
        return {"status": "failed", "error": message or "Shelfmark-TorBox download failed."}
    if state in {"complete", "completed"}:
        return {"status": "complete", "error": ""}
    return {"status": "monitoring", "error": ""}


def add_and_search(title: str, author: str, asin: str = "") -> dict:
    del asin  # direct Shelfmark handoff does not require an Audible ASIN.
    title = (title or "").strip()
    author = (author or "").strip()
    if not title:
        return {"ok": False, "detail": "Refusing audiobook request without a title."}

    try:
        session = _session()
        releases = _search_once(session, title, author)
        chosen, candidates = _choose_release(releases, title, author)
        if chosen is None:
            return {
                "ok": False,
                "detail": (
                    f"Shelfmark-TorBox found {len(releases)} release(s), but none passed "
                    "the conservative single-audiobook torrent checks. Nothing was queued."
                ),
            }

        ref = _queue_release(session, chosen, title, author)
        if not ref:
            return {
                "ok": False,
                "detail": (
                    "Shelfmark-TorBox accepted the release but returned no monitorable "
                    "task/source ID."
                ),
            }

        picked = str(chosen.get("title") or title)
        log.info("direct audiobook queued title=%r author=%r release=%r candidates=%s ref=%r",
                 title, author, picked, candidates, ref)
        return {
            "ok": True,
            "ref": ref,
            "detail": f"Queued one audiobook torrent through Shelfmark-TorBox: {picked}",
        }
    except AudiobookShelfmarkError as exc:
        log.warning("direct audiobook handoff failed for %r: %s", title, exc)
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        log.exception("unexpected direct audiobook handoff failure for %r", title)
        return {"ok": False, "detail": f"Unexpected Shelfmark-TorBox handoff error: {exc}"}
