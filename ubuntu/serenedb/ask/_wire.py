"""Cross-zone bindings — зоны не импортируют друг друга напрямую."""
from __future__ import annotations

_SKIP = frozenset({
    "__name__", "__doc__", "__package__", "__loader__",
    "__spec__", "__file__", "__cached__", "__annotations__",
})
_ZONES: list[tuple[str, dict]] = []


def register_zone(module_name: str, namespace: dict) -> None:
    _ZONES.append((module_name, namespace))


def apply_bindings(namespace: dict) -> None:
    """Inject symbols from already-loaded zones (module-level init in later zones)."""
    merged: dict = {}
    for _, g in _ZONES:
        for k, v in g.items():
            if k in _SKIP:
                continue
            merged[k] = v
    namespace.update(merged)


def wire_all() -> dict:
    """Merge all zone namespaces; every zone sees the same symbols."""
    merged: dict = {}
    for _, g in _ZONES:
        for k, v in g.items():
            if k in _SKIP:
                continue
            merged[k] = v
    for _, g in _ZONES:
        g.update(merged)
    return dict(merged)


def merged_public() -> dict:
    return wire_all() if not _ZONES else {k: v for k, v in _ZONES[-1][1].items() if k not in _SKIP}
