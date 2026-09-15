'''Controlled Stackarr -> Shelfmark ebook handoff.

Safety rules for the initial ebook path:
- ebook requests only; audiobook handoff is deliberately disabled here
- one Shelfmark /api/releases call per requested book
- Prowlarr release source only
- NZB protocol only
- EPUB/PDF only
- expand_search=false
- no author-wide or series-wide acquisition logic
- no can_grab() release search

The existing audiobook system is intentionally not touched by this module.
'''

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from . import config, db

log = logging.getLogger("stackarr.shelfmark")

_SEARCH_TIMEOUT = 180
_API_TIMEOUT = 30


class ShelfmarkError(RuntimeError):
    '''A controlled handoff failure that is safe to show in Stackarr.'''


def url() -> str:
    return db.setting("shelfmark_ebook_url", config.SHELFMARK_EBOOK_URL).rstrip("/")


def username() -> str:
    return db.setting("shelfmark_ebook_username", config.SHELFMARK_EBOOK_USERNAME)


def password() -> str:
    return db.setting("shelfmark_ebook_password", config.SHELFMARK_EBOOK_PASSWORD)


def source() -> str:
    value = db.setting("shelfmark_ebook_source", config.SHELFMARK_EBOOK_SOURCE)
    return (value or "prowlarr").strip().lower()


def configured() -> bool:
    return bool(url())


def monitored_keys() -> set[str]:
    '''Compatibility with Stackarr's old Shelfmark integration.'''
    return set()


def mark_read(title: str, author: str) -> bool:
    '''Shelfmark has no Shelfmark-style monitor flag to disable.'''
    return False


def can_grab(title: str, author: str) -> bool:
    '''Cheap configuration check only; deliberately does not search Prowlarr.'''
    return configured()


def task_statuses() -> dict[str, dict[str, Any]]:
    """Return Shelfmark activity indexed by its exact task/source ID."""
    try:
        session = _session()
        r = session.get(
            f"{url()}/api/activity/snapshot",
            timeout=_API_TIMEOUT,
        )
        if not r.ok:
            raise ShelfmarkError(
                f"Shelfmark activity returned HTTP {r.status_code}."
            )

        data = r.json()
        buckets = data.get("status") if isinstance(data, dict) else None
        if not isinstance(buckets, dict):
            return {}

        out: dict[str, dict[str, Any]] = {}

        for state, entries in buckets.items():
            if not isinstance(entries, dict):
                continue

            for task_id, payload in entries.items():
                item = dict(payload) if isinstance(payload, dict) else {}
                item["state"] = str(state).strip().lower()
                out[str(task_id)] = item

        return out

    except (requests.RequestException, ValueError, ShelfmarkError) as exc:
        log.warning("ebook Shelfmark activity lookup failed: %s", exc)
        return {}


def queue_status() -> dict[str, str]:
    """Compatibility status map keyed by exact Shelfmark task/source ID."""
    out: dict[str, str] = {}

    for task_id, item in task_statuses().items():
        state = str(item.get("state") or "").lower()

        if state == "error":
            out[task_id] = "failed"
        elif state == "cancelled":
            out[task_id] = "failed"
        else:
            # Shelfmark completion still waits for Kavita/library reconciliation
            # before Stackarr declares the request available.
            out[task_id] = "handed"

    return out


def health() -> list[dict[str, str]]:
    if not configured():
        return [{"type": "error", "message": "Shelfmark ebook URL is not configured."}]
    try:
        r = requests.get(f"{url()}/api/health", timeout=15)
        if r.ok:
            return []
        return [{
            "type": "error",
            "message": f"Shelfmark ebook health check returned HTTP {r.status_code}.",
        }]
    except requests.RequestException as exc:
        return [{"type": "error", "message": f"Shelfmark ebook is unreachable: {exc}"}]


def _session() -> requests.Session:
    if not configured():
        raise ShelfmarkError("Libraseer isn't connected to the ebook Shelfmark yet.")

    user = username().strip()
    secret = password()

    if bool(user) != bool(secret):
        raise ShelfmarkError(
            "Shelfmark ebook authentication is incomplete: set both username and password."
        )

    s = requests.Session()
    s.headers.update({"Accept": "application/json"})

    # No credentials means intentionally try Shelfmark without local login.
    if not user:
        return s

    try:
        r = s.post(
            f"{url()}/api/auth/login",
            json={"username": user, "password": secret, "remember_me": True},
            timeout=_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ShelfmarkError(f"Could not reach ebook Shelfmark login: {exc}") from exc

    if r.status_code in (401, 403):
        raise ShelfmarkError("Ebook Shelfmark rejected the configured username/password.")
    if r.status_code == 429:
        raise ShelfmarkError("Ebook Shelfmark login is temporarily rate-limited.")
    if not r.ok:
        raise ShelfmarkError(f"Ebook Shelfmark login failed with HTTP {r.status_code}.")

    return s


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


_FOREIGN_LANGUAGE_MARKERS = {
    "arabic",
    "chinese",
    "czech",
    "danish",
    "dutch",
    "finnish",
    "french",
    "german",
    "greek",
    "hebrew",
    "hungarian",
    "indonesian",
    "italian",
    "japanese",
    "korean",
    "norwegian",
    "polish",
    "portuguese",
    "romanian",
    "russian",
    "spanish",
    "swedish",
    "thai",
    "turkish",
    "vietnamese",
}


def explicit_foreign_language(release_title: str, wanted_title: str) -> str:
    """Return an explicit non-English release-language marker, if present.

    Remove the requested book title first so a legitimate title containing
    words such as 'French' is not accidentally rejected.
    """
    release_key = _norm(release_title)
    wanted_key = _norm(wanted_title)

    if wanted_key and wanted_key in release_key:
        release_key = release_key.replace(wanted_key, " ", 1)

    tokens = set(release_key.split())

    for marker in sorted(_FOREIGN_LANGUAGE_MARKERS):
        if marker in tokens:
            return marker

    return ""


def _release_format(release: dict[str, Any]) -> str:
    values: list[str] = []

    fmt = release.get("format")
    if isinstance(fmt, str):
        values.append(fmt)

    title = release.get("title")
    if isinstance(title, str):
        values.append(title)

    extra = release.get("extra")
    if isinstance(extra, dict):
        for key in ("format", "formats", "formats_display"):
            value = extra.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(x) for x in value)

    haystack = " ".join(values).lower()

    if re.search(r"(^|[^a-z0-9])epub([^a-z0-9]|$)", haystack):
        return "epub"
    if re.search(r"(^|[^a-z0-9])pdf([^a-z0-9]|$)", haystack):
        return "pdf"
    return ""


def _score_release(release: dict[str, Any], title: str, author: str) -> int | None:
    import html

    raw_release_title = str(release.get("title") or "")
    raw_unescaped = html.unescape(raw_release_title)
    release_title = _norm(raw_unescaped)
    wanted_title = _norm(title)

    release_words = release_title.split()
    wanted_words = wanted_title.split()

    if not wanted_words:
        return None

    def find_sequence(haystack: list[str], needle: list[str]) -> list[int]:
        if not needle or len(needle) > len(haystack):
            return []
        width = len(needle)
        return [
            i
            for i in range(len(haystack) - width + 1)
            if haystack[i:i + width] == needle
        ]

    title_positions = find_sequence(release_words, wanted_words)
    if not title_positions:
        return None

    # Do not mistake a requested title used only as a numbered series label
    # for the actual book title, e.g.
    # "Tich Brewster - [Angels & Demons 01] - Devada".
    for bracket in re.finditer(r"\[([^\]]+)\]|\(([^)]+)\)", raw_unescaped):
        bracket_key = _norm(bracket.group(1) or bracket.group(2))

        if not re.fullmatch(
            re.escape(wanted_title) + r"\s+(?:book\s+)?\d+(?:\.\d+)?",
            bracket_key,
        ):
            continue

        after = _norm(raw_unescaped[bracket.end():])

        if after.startswith(wanted_title):
            continue

        metadata = {"retail", "epub", "ebook", "pdf", "edition", "uk", "us"}
        meaningful = [
            word for word in after.split()
            if word not in metadata and not word.isdigit()
        ]
        if meaningful:
            return None

    if explicit_foreign_language(raw_unescaped, title):
        return None

    if str(release.get("source") or "").strip().lower() != source():
        return None
    if str(release.get("protocol") or "").strip().lower() != "nzb":
        return None

    # Never let contradictory upstream metadata turn an obvious audiobook
    # release into an ebook candidate.
    audio_markers = {
        "mp3", "m4b", "m4a", "aac", "audiobook", "audible",
    }
    if any(word in audio_markers for word in release_words):
        return None

    fmt = _release_format(release)
    if fmt not in {"epub", "pdf"}:
        return None

    # Split only on deliberate release-field separators. Do not split colons:
    # "The Bell Jar: A Biography" must remain one title-like field.
    segments = [
        _norm(part)
        for part in re.split(r"\s+(?:-|–|—|\|)\s+|\|", raw_unescaped)
        if _norm(part)
    ]
    exact_title_segment = wanted_title in segments

    author_words = [
        word for word in _norm(author).split()
        if len(word) >= 2
    ]
    full_author_positions = find_sequence(release_words, author_words)
    surname_present = bool(author_words and author_words[-1] in release_words)
    author_present = bool(full_author_positions or surname_present)

    format_markers = {"epub", "ebook", "pdf", "mobi", "azw", "azw3"}
    metadata_words = {
        # File/source metadata.
        "retail", "epub", "ebook", "pdf", "mobi", "azw", "azw3",
        "kindle", "ocr", "scan", "scanned", "converted", "conversion",
        "fixed", "proof", "arc",
        # Edition metadata.
        "edition", "unabridged", "revised", "updated", "expanded",
        "anniversary", "deluxe", "illustrated", "special",
        "international", "reprint", "complete", "uncut",
        # Structural metadata.
        "novel", "book", "volume", "vol", "version", "by",
        # Locale/language metadata that is not itself a foreign marker.
        "uk", "us", "eng", "english",
        # Connectors useful in legitimate edition text.
        "a", "an", "and", "the", "of", "for", "in", "on", "with",
        "to", "from",
    }

    def harmless(word: str) -> bool:
        return (
            word in metadata_words
            or word.isdigit()
            or bool(re.fullmatch(r"(?:18|19|20)\d\d", word))
            or bool(re.fullmatch(r"v\d+(?:\d+)?", word))
            or bool(re.fullmatch(r"\d+(?:st|nd|rd|th)", word))
        )

    first_format = next(
        (i for i, word in enumerate(release_words) if word in format_markers),
        len(release_words),
    )
    core_words = release_words[:first_format]

    # A pack/omnibus must never substitute for a single requested work unless
    # the requested title itself explicitly contains the same pack wording.
    pack_terms = (
        "box set",
        "boxset",
        "complete series",
        "complete collection",
        "omnibus",
        "books 1 2",
        "books 1 3",
        "books 1 4",
        "books 1 5",
    )
    if any(
        term in release_title and term not in wanted_title
        for term in pack_terms
    ):
        return None

    short_title = len(wanted_words) <= 3

    if short_title:
        release_word_set = set(release_words)

        # Short titles need a stronger author identity check. A surname match
        # alone is unsafe: Brian Herbert must not satisfy Frank Herbert.
        strong_author_present = False

        if author_words:
            if len(author_words) == 1:
                strong_author_present = author_words[0] in release_word_set
            else:
                all_author_words_present = all(
                    word in release_word_set
                    for word in author_words
                )
                surname_present = author_words[-1] in release_word_set
                first_initial_present = (
                    bool(author_words[0])
                    and author_words[0][0] in release_word_set
                )
                strong_author_present = (
                    all_author_words_present
                    or (surname_present and first_initial_present)
                )

                # A shared surname with a conflicting/missing given-name anchor
                # is especially dangerous for short titles.
                if surname_present and not strong_author_present:
                    return None

        if exact_title_segment:
            title_segment_index = segments.index(wanted_title)
            segment_words = [segment.split() for segment in segments]

            format_segment_positions = [
                i
                for i, words in enumerate(segment_words)
                if any(word in format_markers for word in words)
                and i > title_segment_index
            ]

            if format_segment_positions:
                last_segment = min(format_segment_positions)
            else:
                last_segment = len(segment_words) - 1

            publisher_tail_words = {
                "books", "press", "publishing", "publisher",
                "publishers", "classics", "editions", "house",
            }

            substantive: list[str] = []

            for i in range(title_segment_index + 1, last_segment + 1):
                words = list(segment_words[i])

                # A format token may share a segment with bad title text:
                # "Dune Encyclopedia (pdf)" must inspect "Dune Encyclopedia"
                # rather than treating the whole segment as format metadata.
                marker_positions = [
                    n
                    for n, word in enumerate(words)
                    if word in format_markers
                ]
                if marker_positions:
                    words = words[:min(marker_positions)]

                if not words:
                    continue

                words = [
                    word
                    for word in words
                    if word not in set(author_words)
                ]

                if len(author_words) >= 2 and author_words[0]:
                    initial = author_words[0][0]
                    words = [
                        word
                        for word in words
                        if word != initial
                    ]

                if not words:
                    continue

                # Common publisher/imprint fields are legitimate noise.
                if words[-1] in publisher_tail_words:
                    continue

                substantive.extend(
                    word
                    for word in words
                    if len(word) >= 2
                    and not harmless(word)
                )

            if substantive:
                return None

            # A bare exact short title at the start ("Dune - EPUB") can be
            # useful even without author metadata. If the title occurs later,
            # require a convincing author anchor.
            if (
                author_words
                and not strong_author_present
                and title_segment_index != 0
            ):
                return None

        else:
            # No cleanly-delimited exact title: short titles require a strong
            # author anchor and no unexplained bibliographic words.
            if author_words and not strong_author_present:
                return None

            remaining = list(core_words)
            core_title_positions = find_sequence(remaining, wanted_words)
            if not core_title_positions:
                return None

            pos = core_title_positions[0]
            del remaining[pos:pos + len(wanted_words)]

            if author_words:
                author_pos = find_sequence(remaining, author_words)

                if author_pos:
                    apos = author_pos[0]
                    del remaining[apos:apos + len(author_words)]
                else:
                    remaining = [
                        word
                        for word in remaining
                        if word not in set(author_words)
                    ]

                if len(author_words) >= 2 and author_words[0]:
                    initial = author_words[0][0]
                    remaining = [
                        word
                        for word in remaining
                        if word != initial
                    ]

            substantive = [
                word
                for word in remaining
                if len(word) >= 2
                and not harmless(word)
            ]

            if substantive:
                return None

    # Longer titles remain tolerant. Extra text is penalised rather than
    # automatically rejected unless one of the hard safety rules above fired.
    suspicious_prefix_penalty = 0
    suspicious_suffix_penalty = 0

    if not exact_title_segment:
        title_pos = title_positions[0]
        prefix_words = release_words[:title_pos]
        suffix_words = release_words[title_pos + len(wanted_words):]

        prefix_allowed = set(wanted_words) | set(author_words) | metadata_words
        unexplained_prefix = [
            word
            for word in prefix_words
            if len(word) >= 3
            and not word.isdigit()
            and word not in prefix_allowed
        ]
        if len(unexplained_prefix) >= 2:
            suspicious_prefix_penalty = min(
                60,
                len(unexplained_prefix) * 15,
            )

        suffix_allowed = set(author_words) | metadata_words
        unexplained_suffix = [
            word
            for word in suffix_words
            if len(word) >= 3
            and not word.isdigit()
            and word not in suffix_allowed
        ]
        if len(unexplained_suffix) >= 3:
            suspicious_suffix_penalty = min(
                60,
                len(unexplained_suffix) * 12,
            )

    score = 100 - suspicious_prefix_penalty - suspicious_suffix_penalty

    if release_title == wanted_title:
        score += 90
    elif exact_title_segment:
        score += 70
    elif title_positions[0] == 0:
        score += 45
    else:
        score += 20

    matched_author_words = [
        word
        for word in author_words
        if word in release_words
    ]
    score += len(matched_author_words) * 8

    if author_words and not author_present:
        score -= 30

    score += 30 if fmt == "epub" else 10
    return score


def _choose_release(
    releases: list[dict[str, Any]],
    title: str,
    author: str,
    excluded_refs: set[str] | None = None,
    excluded_titles: set[str] | None = None,
) -> tuple[dict[str, Any] | None, int]:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    excluded_refs = excluded_refs or set()
    excluded_title_keys = {
        _norm(value)
        for value in (excluded_titles or set())
        if _norm(value)
    }

    for idx, release in enumerate(releases):
        if not isinstance(release, dict):
            continue

        release_ref = str(release.get("source_id") or "").strip()
        if release_ref and release_ref in excluded_refs:
            continue

        release_title_key = _norm(str(release.get("title") or ""))
        if release_title_key and release_title_key in excluded_title_keys:
            continue

        score = _score_release(release, title, author)
        if score is None or score < 0:
            continue
        ranked.append((score, -idx, release))

    if not ranked:
        return None, 0

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2], len(ranked)


def _search_once(
    session: requests.Session, title: str, author: str
) -> list[dict[str, Any]]:
    # Use Shelfmark's manual metadata context and explicitly target Prowlarr.
    # manual_query forces exactly one raw search variant.
    params = {
        "provider": "manual",
        "book_id": f"stackarr:{title.strip()}",
        "source": source(),
        "title": title,
        "author": author,
        "manual_query": title,
        "content_type": "ebook",
        "expand_search": "false",
    }

    try:
        r = session.get(
            f"{url()}/api/releases",
            params=params,
            timeout=_SEARCH_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ShelfmarkError(f"Ebook release search failed: {exc}") from exc

    if r.status_code in (401, 403):
        raise ShelfmarkError(
            "Ebook Shelfmark requires authentication or rejected this session."
        )
    if r.status_code == 429:
        raise ShelfmarkError(
            "Ebook Shelfmark/Prowlarr is rate-limited; no second search was attempted."
        )
    if not r.ok:
        raise ShelfmarkError(
            f"Ebook Shelfmark release search returned HTTP {r.status_code}; "
            "no second search was attempted."
        )

    try:
        data = r.json()
    except ValueError as exc:
        raise ShelfmarkError("Ebook Shelfmark returned invalid JSON.") from exc

    releases = data.get("releases", []) if isinstance(data, dict) else []
    if not isinstance(releases, list):
        raise ShelfmarkError("Ebook Shelfmark returned an invalid releases list.")

    return releases


def _download_release(
    session: requests.Session,
    release: dict[str, Any],
    requested_title: str,
    requested_author: str,
) -> str:
    # Reuse the SAME release returned by the one search. No second lookup.
    payload = dict(release)
    payload["content_type"] = "ebook"

    if not payload.get("title"):
        payload["title"] = requested_title

    extra = payload.get("extra")
    release_author = extra.get("author") if isinstance(extra, dict) else None

    # Shelfmark uses task.author for the {Author} destination folder.
    # Prefer Stackarr's canonical requested author over release contributors.
    canonical_author = (requested_author or "").strip()
    if canonical_author:
        payload["author"] = canonical_author
    elif not payload.get("author"):
        payload["author"] = release_author

    try:
        r = session.post(
            f"{url()}/api/releases/download",
            json=payload,
            timeout=_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ShelfmarkError(f"Could not queue ebook release: {exc}") from exc

    if r.status_code in (401, 403):
        raise ShelfmarkError("Ebook Shelfmark refused the selected release.")
    if r.status_code == 429:
        raise ShelfmarkError(
            "Ebook Shelfmark is rate-limited while queueing the selected release."
        )
    if not r.ok:
        detail = ""
        try:
            body = r.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("error") or "")
        except ValueError:
            pass
        suffix = f": {detail}" if detail else ""
        raise ShelfmarkError(
            f"Ebook Shelfmark download queue returned HTTP {r.status_code}{suffix}"
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

    # Shelfmark v1.3.13 returns only {"status": "queued", "priority": ...}
    # from /api/releases/download. The release source_id is the exact task ID
    # Shelfmark uses in its queue/activity API, so preserve that as our ref.
    source_id = payload.get("source_id")
    if source_id is not None and str(source_id).strip():
        return str(source_id)

    return ""



def _fallback_search_title(title: str) -> str:
    """Return one conservative alternate acquisition title.

    Hardcover sometimes uses a canonical alternate-title form such as:
      "The Hobbit, or There and Back Again"

    Usenet releases overwhelmingly use just:
      "The Hobbit"

    Only collapse the explicit ", or ..." form. Do not generally strip
    subtitles or weaken release matching.
    """
    title = (title or "").strip()
    lower = title.lower()
    pos = lower.find(", or ")

    if pos <= 0:
        return ""

    short = title[:pos].strip(" ,:;-")
    if len(_norm(short).split()) < 2:
        return ""

    return short


def add_and_search(
    title: str,
    author: str,
    asin: str = "",
    fmt: str = "ebook",
    root_folder_override: str = "",
    excluded_refs: set[str] | None = None,
    excluded_titles: set[str] | None = None,
) -> dict[str, Any]:
    '''Search once, select one conservative NZB ebook release, queue it once.'''
    del asin, root_folder_override

    if fmt != "ebook":
        return {
            "ok": False,
            "detail": (
                "Audiobook handoff is deliberately disabled in the Shelfmark ebook "
                "test branch. The existing AudiobookRequest path remains untouched."
            ),
        }

    title = (title or "").strip()
    author = (author or "").strip()

    if not title:
        return {"ok": False, "detail": "Refusing ebook request without a specific title."}

    try:
        session = _session()

        search_titles = [title]
        fallback_title = _fallback_search_title(title)

        if fallback_title and _norm(fallback_title) != _norm(title):
            search_titles.append(fallback_title)

        chosen = None
        candidate_count = 0
        searches = []

        for search_title in search_titles:
            releases = _search_once(session, search_title, author)
            chosen, candidate_count = _choose_release(
                releases,
                search_title,
                author,
                excluded_refs=excluded_refs,
                excluded_titles=excluded_titles,
            )
            searches.append((search_title, len(releases), candidate_count))

            if chosen is not None:
                break

        if chosen is None:
            if len(searches) > 1:
                summary = "; ".join(
                    f"{q!r}: {count} release(s)"
                    for q, count, _ in searches
                )
                detail = (
                    "Shelfmark tried the canonical title and one conservative "
                    f"alternate-title search ({summary}), but none passed the "
                    "safe single-book NZB EPUB/PDF checks. Nothing was queued."
                )
            else:
                detail = (
                    f"Shelfmark searched once and found {searches[0][1]} release(s), "
                    "but none passed the safe single-book NZB EPUB/PDF checks. "
                    "Nothing was queued."
                )

            return {"ok": False, "detail": detail}

        ref = _download_release(session, chosen, title, author)
        picked = str(chosen.get("title") or title)
        format_name = _release_format(chosen).upper()

        log.info(
            "ebook handoff queued title=%r author=%r release=%r candidates=%s ref=%r",
            title,
            author,
            picked,
            candidate_count,
            ref,
        )

        return {
            "ok": True,
            "ref": ref,
            "detail": f"Queued one {format_name} NZB through ebook Shelfmark: {picked}",
        }

    except ShelfmarkError as exc:
        log.warning("ebook Shelfmark handoff failed for %r: %s", title, exc)
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        log.exception("unexpected ebook Shelfmark handoff failure for %r", title)
        return {
            "ok": False,
            "detail": f"Unexpected ebook Shelfmark handoff error: {exc}",
        }
