"""Low-cardinality Harness counters that never carry resume or message data."""

from collections import Counter
from threading import RLock


METRIC_NAMES = frozenset({
    "interview_turns_total",
    "interview_fallbacks_total",
    "persistence_errors_total",
    "workflow_errors_total",
    "workflow_cleanup_threads_total",
})


class HarnessMetrics:
    def __init__(self):
        self._lock = RLock()
        self._counters = Counter()

    def increment(self, name: str, amount: int = 1):
        if name not in METRIC_NAMES:
            raise ValueError(f"unsupported harness metric: {name}")
        with self._lock:
            self._counters[name] += max(0, int(amount))

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {name: int(self._counters.get(name, 0)) for name in sorted(METRIC_NAMES)}


harness_metrics = HarnessMetrics()
