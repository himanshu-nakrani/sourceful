import threading
from collections import defaultdict
from typing import Iterable


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._hist_sums: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._hist_counts: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None = None) -> tuple[str, tuple[tuple[str, str], ...]]:
        frozen = tuple(sorted((labels or {}).items()))
        return name, frozen

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += amount

    def observe(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            key = self._key(name, labels)
            self._hist_sums[key] += value
            self._hist_counts[key] += 1

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = value

    @staticmethod
    def _render_line(name: str, value: float, labels: Iterable[tuple[str, str]]) -> str:
        items = list(labels)
        if not items:
            return f"{name} {value}"
        label_text = ",".join(f'{k}="{v}"' for k, v in items)
        return f"{name}{{{label_text}}} {value}"

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(self._render_line(name, value, labels))
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(self._render_line(name, value, labels))
            for (name, labels), value in sorted(self._hist_counts.items()):
                lines.append(self._render_line(f"{name}_count", value, labels))
            for (name, labels), value in sorted(self._hist_sums.items()):
                lines.append(self._render_line(f"{name}_sum", value, labels))
        return "\n".join(lines) + ("\n" if lines else "")


metrics = MetricsRegistry()
