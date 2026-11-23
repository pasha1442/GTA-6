"""Chat spike detection.

Counts messages per second, then compares the most recent window against a
rolling baseline made of earlier windows from the same stream.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Spike:
    ts: float        # wall-clock time the spike was detected
    count: int       # messages in the spike window
    baseline: float  # average messages per window before the spike
    score: float     # count / baseline (how many times above normal)


class SpikeDetector:
    def __init__(
        self,
        window: int = 10,        # seconds of chat that make up "right now"
        baseline: int = 300,     # seconds of history used as "normal"
        warmup: int = 60,        # history needed before any spike can fire
        factor: float = 3.0,     # spike must be this many times the average
        zscore: float = 3.0,     # ...and this many std-devs above it
        min_messages: int = 15,  # ...and at least this many messages
        cooldown: int = 60,      # seconds between two spikes
        delay: float = 0.0,      # judge chat this many seconds late (for chat that arrives in batches)
    ):
        self.delay = delay
        self.window = window
        self.baseline = baseline
        self.warmup = warmup
        self.factor = factor
        self.zscore = zscore
        self.min_messages = min_messages
        self.cooldown = cooldown
        self._counts: dict[int, float] = defaultdict(float)
        self._start: float | None = None
        self._last_spike = -math.inf

    def add(self, ts: float, weight: float = 1.0) -> None:
        """Record one chat message received at wall-clock time `ts`, counted as `weight` messages."""
        if self._start is None:
            self._start = ts
        self._counts[int(ts)] += weight

    def _sum(self, lo: int, hi: int) -> int:
        return sum(self._counts.get(s, 0) for s in range(lo, hi))

    def stats(self, now: float) -> tuple[int, float, float, int]:
        """Return (recent count, baseline mean, baseline std, baseline buckets)."""
        now -= self.delay
        if self._start is None:
            self._start = now
        end = int(now)  # the current second is still filling up, so exclude it
        w = self.window
        recent = self._sum(end - w, end)
        base_end = end - w
        available = base_end - int(self._start)
        n = max(0, min(self.baseline, available) // w)
        buckets = [self._sum(base_end - (i + 1) * w, base_end - i * w) for i in range(n)]
        if not buckets:
            return recent, 0.0, 0.0, 0
        mean = sum(buckets) / n
        std = math.sqrt(sum((b - mean) ** 2 for b in buckets) / n)
        return recent, mean, std, n

    def check(self, now: float) -> Spike | None:
        """Call about once per second. Returns a Spike when one starts."""
        recent, mean, std, n = self.stats(now)
        now -= self.delay  # the moment being judged
        self._prune(now)
        if n * self.window < self.warmup:
            return None
        if now - self._last_spike < self.cooldown:
            return None
        threshold = max(self.min_messages, mean * self.factor, mean + self.zscore * std)
        if recent < threshold:
            return None
        self._last_spike = now
        return Spike(ts=now, count=recent, baseline=mean, score=recent / max(mean, 1.0))

    def _prune(self, now: float) -> None:
        cutoff = int(now) - self.window - self.baseline - 5
        for s in [s for s in self._counts if s < cutoff]:
            del self._counts[s]
