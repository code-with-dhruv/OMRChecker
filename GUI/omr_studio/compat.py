"""Compatibility shims for running the engine inside a GUI/headless host."""
from __future__ import annotations


def install_monitor_fallback() -> None:
    """The engine queries the monitor size at import time and crashes when no
    display can be enumerated (remote sessions, containers, some Linux setups).
    Fall back to a nominal 1080p monitor instead of failing to start."""
    try:
        import screeninfo
    except ImportError:  # pragma: no cover
        return
    if getattr(screeninfo.get_monitors, "_omr_safe", False):
        return
    original = screeninfo.get_monitors

    def safe_get_monitors(*args, **kwargs):
        try:
            monitors = original(*args, **kwargs)
            if monitors:
                return monitors
        except screeninfo.ScreenInfoError:
            pass
        return [screeninfo.Monitor(0, 0, 1920, 1080, name="fallback", is_primary=True)]

    safe_get_monitors._omr_safe = True  # type: ignore[attr-defined]
    screeninfo.get_monitors = safe_get_monitors
