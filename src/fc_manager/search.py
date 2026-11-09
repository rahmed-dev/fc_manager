"""Ranked search over a fixed list of items, for the search prompts (apps, branches).

FC has no search method that works over GET for these lists, so fcm reads the list once
and searches it locally. The index is built once. Each query is one pass over the entries
with plain string operations, and `heapq.nsmallest` keeps only the best `limit` matches,
so no full sort runs per key press.

Rank of a match, lower is better:
  0  the key equals the query
  1  the key starts with the query
  2  a word of the key or the title starts with the query
  3  the query is inside the key or the title
  4  the letters of the query appear in order in the key or the title
"""

from __future__ import annotations

import heapq
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

DEFAULT_LIMIT = 10
_WORD_SPLIT = re.compile(r"[\s_\-./]+")


def _in_order(query: str, text: str) -> bool:
    """True when the letters of `query` appear in `text` in the same order."""
    it = iter(text)
    return all(char in it for char in query)


@dataclass(frozen=True)
class _Entry(Generic[T]):
    item: T
    key: str  # lowercase
    title: str  # lowercase
    words: tuple[str, ...]
    compact: str  # key and title with no separators, for the in-order match


class SearchIndex(Generic[T]):
    def __init__(
        self,
        items: Sequence[T],
        key: Callable[[T], str],
        title: Callable[[T], str] = lambda _item: "",
    ) -> None:
        self._entries: list[_Entry[T]] = []
        for item in items:
            k, t = key(item).lower(), title(item).lower()
            words = tuple(w for w in _WORD_SPLIT.split(f"{k} {t}") if w)
            self._entries.append(_Entry(item, k, t, words, "".join(words)))

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _rank(entry: _Entry[T], q: str) -> tuple[int, int] | None:
        if entry.key == q:
            return 0, 0
        if entry.key.startswith(q):
            return 1, 0
        for word in entry.words:
            if word.startswith(q):
                return 2, 0
        at = entry.key.find(q)
        if at < 0:
            at = entry.title.find(q)
        if at >= 0:
            return 3, at
        if _in_order(q, entry.key) or _in_order(q, entry.compact):
            return 4, 0
        return None

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[T]:
        """The best `limit` items for `query`, best first. An empty query gives none."""
        q = query.strip().lower()
        if not q:
            return []
        scored = []
        for n, entry in enumerate(self._entries):
            rank = self._rank(entry, q)
            if rank is not None:
                scored.append((rank[0], rank[1], len(entry.key), entry.title, n))
        best = heapq.nsmallest(limit, scored)
        return [self._entries[row[-1]].item for row in best]
