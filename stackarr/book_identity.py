"""Shared conservative work-title and contributor matching.

Verified pen names are explicit aliases; arbitrary shared surnames are not.
Format labels may be ignored only after the requested work is identified.
"""
from __future__ import annotations

import html
import re
import unicodedata

_AUDIO_FORMATS = {"mp3", "m4b", "m4a", "aac", "flac", "ogg", "opus", "zip", "rar", "7z"}

def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _author_names(value: str) -> list[str]:
    # A release may list only one of a book's coauthors. Keep people separate
    # rather than treating "Rob Grant, Doug Naylor" as one four-word name.
    names = [name for part in re.split(r",|;|&|\band\b", html.unescape(value or ""), flags=re.I)
             if (name := _norm(part))]
    # Verified joint pen name, not a heuristic combining any two surnames.
    # https://reddwarf.co.uk/about/index.cfm?category=the-creators
    if set(names) == {"rob grant", "doug naylor"}:
        names.append("grant naylor")
    elif names == ["grant naylor"]:
        names.extend(["rob grant", "doug naylor"])
    return names


def _name_variants(name: str) -> set[str]:
    words = name.split()
    variants = {name}
    if len(words) >= 2:
        variants.add(" ".join([words[0][0], *words[1:]]))
        if all(len(word) == 1 for word in words[:-1]):
            variants.add("".join(words[:-1]) + " " + words[-1])
    return variants


def _author_matches(wanted: str, evidence: str) -> bool:
    evidence = " " + _norm(evidence) + " "
    return any(" " + variant + " " in evidence
               for name in _author_names(wanted) for variant in _name_variants(name))


def _wanted_titles(title: str, subtitle: str = "") -> set[str]:
    keys = {_norm(title)}
    sub = _norm(subtitle)
    if sub and sub not in keys:
        keys.add(_norm(title + " " + subtitle))
        # Distinctive catalogue subtitles sometimes serve as the release title.
        # Generic labels such as "A Novel" must never become standalone aliases.
        if len(sub.split()) >= 3 and not sub.startswith(("a novel", "book ", "the complete")):
            keys.add(sub)
    return keys - {""}


_TITLE_METADATA = _AUDIO_FORMATS | {
    "unabridged", "abridged", "audiobook", "audio", "retail", "audible", "eng", "english",
}


def _release_title_key(
    value: str, wanted: set[str], contributors: str, *,
    metadata_words: set[str] | None = None,
) -> str:
    """Remove explicit file/edition metadata, then compare the entire work title.

    Extra bibliographic words stay significant: "Titan", "Better Than Life",
    "Series V to VIII", and "BBC TV Soundtracks" cannot disappear in scoring.
    """
    value = html.unescape(value)
    protected = set(" ".join(wanted).split())
    labels = _TITLE_METADATA if metadata_words is None else metadata_words

    def strip_note(match):
        text = _norm(match.group(0))
        words = text.split()
        if text in wanted:
            return match.group(0)
        technical = labels | {"kbps", "khz", "bit", "stereo", "mono"}
        if words and all(word in technical or word.isdigit() for word in words):
            return " "
        return match.group(0)

    value = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", strip_note, value)
    # A suffix attached directly to a file format is an upload-group label.
    value = re.sub(r"\b(mp3|m4b|m4a|aac|flac|ogg|opus)-(\w+)\b", r"\1", value, flags=re.I)
    value = re.sub(r"\b\d+\s*(?:kbps|khz)\b", " ", value, flags=re.I)
    key = _norm(value)
    for name in _author_names(contributors):
        for variant in sorted(_name_variants(name), key=len, reverse=True):
            if any(variant in title for title in wanted):
                continue
            key = re.sub(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", " ", key)
    key = re.sub(r"\b(?:read by|narrated by)\b", " ", key)
    words = [word for word in key.split() if word not in (labels - protected)]
    while words and words[0] in {"by", "and"} and words[0] not in protected:
        words.pop(0)
    while words and words[-1] in {"by", "and"} and words[-1] not in protected:
        words.pop()
    return " ".join(words)
