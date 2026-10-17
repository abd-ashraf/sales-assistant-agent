"""Keyword search (BM25) over brochure pages: the best-matching pages first."""

import math
import re
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

from sales_assistant.brochures import Page

# Words and numbers: decimals stay whole ("1.35"); hyphens split codes, so "PF DS" finds "PF-DS".
WORD = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")
# The usual Okapi BM25 settings: how quickly repeats of a word stop adding score (K1), and
# how much a long page is held back against a short one (B).
K1 = 1.5
B = 0.75
DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class SearchHit:
    """A page that shares words with the query, and its BM25 score (higher is better)."""

    page: Page
    score: float


def tokenize(text: str) -> list[str]:
    """Return lower-case words and numbers: "Larox® PF-DS, 1.35 t" -> larox, pf, ds, 1.35, t."""
    return WORD.findall(text.lower())


def best_line(text: str, query: str) -> str:
    """Return the line of `text` sharing the most words with `query` (the first, on a tie)."""
    terms = set(tokenize(query))
    return max(text.splitlines(), key=lambda line: len(terms & set(tokenize(line))), default="")


class PageIndex:
    """A BM25 index over brochure pages."""

    def __init__(self, pages: list[Page]) -> None:
        self._pages = pages
        self._term_counts = [Counter(tokenize(page.text)) for page in pages]
        self._lengths = [sum(counts.values()) for counts in self._term_counts]
        self._average_length = sum(self._lengths) / max(len(pages), 1)
        pages_with_term = Counter(term for counts in self._term_counts for term in counts)
        # Rare words weigh more: a word found on few pages says more than one found on most.
        self._idf = {
            term: math.log(1 + (len(pages) - count + 0.5) / (count + 0.5))
            for term, count in pages_with_term.items()
        }

    @property
    def brochures(self) -> set[str]:
        """The file names of the brochures in the index."""
        return {page.brochure for page in self._pages}

    def search(
        self, query: str, brochures: Collection[str] | None = None, top_k: int = DEFAULT_TOP_K
    ) -> list[SearchHit]:
        """Return up to `top_k` pages sharing words with `query`, best first.

        `brochures`, when given, limits the search to those brochure file names.
        """
        terms = tokenize(query)
        hits = [
            SearchHit(page, self._score(terms, index))
            for index, page in enumerate(self._pages)
            if brochures is None or page.brochure in brochures
        ]
        matches = [hit for hit in hits if hit.score > 0]
        return sorted(matches, key=lambda hit: hit.score, reverse=True)[:top_k]

    def _score(self, terms: list[str], index: int) -> float:
        counts = self._term_counts[index]
        matched = [term for term in terms if term in counts]
        if not matched:
            return 0.0
        length_factor = K1 * (1 - B + B * self._lengths[index] / self._average_length)
        return sum(
            self._idf[term] * counts[term] * (K1 + 1) / (counts[term] + length_factor)
            for term in matched
        )
