"""Line wrapping and segment splitting for subtitle events.

We wrap ourselves (WrapStyle: 2 disables libass auto-wrap) so the preview and the
burn-in render break lines identically.
"""

from __future__ import annotations

from dataclasses import dataclass

from subtitle_studio.schema import Segment

CPS_WARN_THRESHOLD = 20.0  # chars/second above which reading gets uncomfortable


def wrap_text(text: str, max_chars: int) -> list[str]:
    """Greedy fill to max_chars at word boundaries, then balance the last two
    lines (prefer near-equal lengths; prefer breaking after punctuation)."""
    words = text.split()
    if not words:
        return []
    lines: list[list[str]] = [[]]
    for word in words:
        candidate = " ".join(lines[-1] + [word])
        if lines[-1] and len(candidate) > max_chars:
            lines.append([word])
        else:
            lines[-1].append(word)
    if len(lines) >= 2:
        lines[-2], lines[-1] = _balance(lines[-2], lines[-1], max_chars)
    return [" ".join(line) for line in lines if line]


def _balance(a: list[str], b: list[str], max_chars: int) -> tuple[list[str], list[str]]:
    """Move trailing words of `a` down to `b` while it improves balance."""
    best = (a, b)
    best_score = _balance_score(a, b)
    while len(a) > 1:
        a, b = a[:-1], [a[-1]] + b
        if len(" ".join(b)) > max_chars:
            break
        score = _balance_score(a, b)
        if score < best_score:
            best, best_score = (a, b), score
    return best


def _balance_score(a: list[str], b: list[str]) -> float:
    len_a, len_b = len(" ".join(a)), len(" ".join(b))
    score = abs(len_a - len_b)
    if a and a[-1][-1] in ",.;:!?…»)”": # a break after punctuation reads better
        score -= 2
    return score


def _pack(tokens: list[str], width: int, word_cap: int) -> list[list[int]]:
    """Greedy-fill token INDICES into chunks within `width` chars / `word_cap` words."""
    chunks: list[list[int]] = []
    current: list[int] = []
    for i in range(len(tokens)):
        candidate = len(" ".join(tokens[j] for j in current + [i]))
        if current and (candidate > width or len(current) >= word_cap):
            chunks.append(current)
            current = [i]
        else:
            current.append(i)
    if current:
        chunks.append(current)
    return chunks


def _balanced_pack(tokens: list[str], max_chars: int, word_cap: int) -> list[list[int]]:
    """The same number of chunks a greedy fill needs, spread evenly.

    Filling each subtitle to the character cap pushes the remainder into the
    last one, which is how a sentence ends on a single stranded word --
    "...as a full-stack web" / "developer". Keeping the chunk COUNT and packing
    it at the narrowest width that still achieves it spreads the words instead,
    so the final subtitle is a phrase like the others.
    """
    target = len(_pack(tokens, max_chars, word_cap))
    lo, hi, best = 1, max_chars, max_chars
    while lo <= hi:
        mid = (lo + hi) // 2
        if len(_pack(tokens, mid, word_cap)) <= target:
            best, hi = mid, mid - 1
        else:
            lo = mid + 1
    return _pack(tokens, best, word_cap)


@dataclass
class Event:
    start: float
    end: float
    lines: list[str]
    speaker: str | None
    cps: float

    @property
    def text(self) -> str:
        return r"\N".join(self.lines)


def segment_events(segment: Segment, max_line_chars: int, max_lines: int, max_words: int = 0) -> list[Event]:
    """One segment -> one or more display events.

    Overlong segments split at word boundaries using word timestamps when
    available (accurate sub-timing) or proportionally by characters (translated
    variants, which carry no word timings). `max_words` > 0 additionally caps
    the number of words shown per subtitle event.
    """
    chunks = _split_words(segment, max_line_chars * max_lines, max_words)
    events = []
    for start, end, text in chunks:
        duration = max(end - start, 0.001)
        events.append(
            Event(
                start=start,
                end=end,
                lines=wrap_text(text, max_line_chars),
                speaker=segment.speaker,
                cps=round(len(text) / duration, 1),
            )
        )
    return events


def _split_words(segment: Segment, max_chars: int, max_words: int = 0) -> list[tuple[float, float, str]]:
    text = segment.text.strip()
    word_cap = max_words if max_words > 0 else 10**9
    if len(text) <= max_chars and len(text.split()) <= word_cap:
        return [(segment.start, segment.end, text)]

    words = segment.words
    if words and " ".join(w.word.strip() for w in words).split() != text.split():
        words = []  # stale words from an edited text must never reach the screen
    if words:  # timed split
        tokens = [w.word.strip() for w in words]
        return [
            (words[idx[0]].start, words[idx[-1]].end, " ".join(tokens[j] for j in idx))
            for idx in _balanced_pack(tokens, max_chars, word_cap)
        ]

    # proportional split (no word timings)
    tokens = text.split()
    parts = [
        " ".join(tokens[j] for j in idx)
        for idx in _balanced_pack(tokens, max_chars, word_cap)
    ]
    total_chars = sum(len(p) for p in parts) or 1
    duration = segment.end - segment.start
    chunks = []
    cursor = segment.start
    for part in parts:
        share = duration * (len(part) / total_chars)
        chunks.append((round(cursor, 3), round(cursor + share, 3), part))
        cursor += share
    if chunks:
        last_start, _, last_text = chunks[-1]
        chunks[-1] = (last_start, segment.end, last_text)  # absorb rounding drift
    return chunks
