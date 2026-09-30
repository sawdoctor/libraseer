"""Small in-process catalogue cache.

Catalogue metadata is public and shared across users, so it is safe to cache
globally. Authentication, requests, ratings, and other user state never enter
this cache.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

_lock = threading.RLock()
_queries: dict[tuple[str, tuple[str, ...], int], tuple[float, list[dict[str, Any]]]] = {}
_items: dict[str, tuple[float, dict[str, Any]]] = {}
QUERY_TTL = 15 * 60
ITEM_TTL = 24 * 60 * 60
MAX_QUERIES = 128
MAX_ITEMS = 512


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _fresh(entry):
    if not entry or entry[0] <= time.monotonic():
        return None
    return entry[1]


def get_query(query: str, active: list[str], limit: int) -> list[dict[str, Any]] | None:
    key = (_norm(query), tuple(active), int(limit))
    with _lock:
        value = _fresh(_queries.get(key))
        if value is None:
            _queries.pop(key, None)
            return None
        return [dict(item) for item in value]


def set_query(query: str, active: list[str], limit: int, results: list[dict[str, Any]]) -> None:
    # Keep a transient empty response briefly so a failing provider is not
    # hammered, but let a user retry much sooner than a successful search.
    expires = time.monotonic() + (QUERY_TTL if results else 60)
    copied = [dict(item) for item in results]
    with _lock:
        if len(_queries) >= MAX_QUERIES:
            oldest = min(_queries, key=lambda key: _queries[key][0])
            _queries.pop(oldest, None)
        _queries[(_norm(query), tuple(active), int(limit))] = (expires, copied)
    remember(copied)


def remember(results: list[dict[str, Any]]) -> None:
    expires = time.monotonic() + ITEM_TTL
    with _lock:
        for item in results:
            identity = str(item.get("asin") or item.get("id") or "").strip()
            if not identity:
                continue
            if len(_items) >= MAX_ITEMS and identity not in _items:
                oldest = min(_items, key=lambda key: _items[key][0])
                _items.pop(oldest, None)
            _items[identity] = (expires, dict(item))


def get_item(identity: str) -> dict[str, Any] | None:
    with _lock:
        value = _fresh(_items.get(identity))
        if value is None:
            _items.pop(identity, None)
            return None
        return dict(value)


def suggest(query: str, active: list[str], limit: int = 7) -> list[dict[str, Any]]:
    words = _norm(query).split()
    if not words:
        return []
    allowed = set(active)
    now = time.monotonic()
    matches = []
    with _lock:
        for identity, (expires, item) in list(_items.items()):
            if expires <= now:
                _items.pop(identity, None)
                continue
            if item.get("format") not in allowed:
                continue
            haystack = _norm(" ".join(str(item.get(k) or "") for k in ("title", "author", "series")))
            if all(word in haystack for word in words):
                matches.append(dict(item))
    matches.sort(key=lambda item: (
        0 if _norm(item.get("title", "")) == _norm(query) else
        1 if _norm(query) in _norm(item.get("title", "")) else 2,
        _norm(item.get("title", "")),
    ))
    return matches[:limit]


def clear() -> None:
    """Test helper."""
    with _lock:
        _queries.clear()
        _items.clear()
