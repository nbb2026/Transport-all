"""Pure harmonic mode parsing and multi-pass scheduling calculations."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

DEFAULT_HARMONIC_ORDERS: tuple[int, ...] = (1, 2, 3)

DEFAULT_HARMONIC_MODE_ORDERS: dict[str, tuple[int, ...]] = {
    "1": (1,),
    "2": (2,),
    "3": (3,),
    "1+2": (1, 2),
    "1+2+3": (1, 2, 3),
}

DEFAULT_HARMONIC_CHOICES: tuple[int | str, ...] = (1, 2, 3, "1+2", "1+2+3")

DEFAULT_HARMONIC_LABELS: dict[int, str] = {
    1: "1st harmonic",
    2: "2nd harmonic",
    3: "3rd harmonic",
}

DEFAULT_SR830_HARMONIC_SETTING_KEYS: dict[str, str] = {
    "830_a": "harmonic_a",
    "830_b": "harmonic_b",
    "830_c": "harmonic_c",
}


def parse_harmonic_mode(
    mode: Any,
    mode_orders: Mapping[str, Sequence[int]] | None = None,
) -> tuple[int, ...] | Any:
    """Parse a harmonic mode selection into harmonic orders.

    Accepts "1", "2", "3", "1+2", "1+2+3" (or integer 1, 2, 3), with leading
    and trailing whitespace stripped.

    Raises ValueError("Select harmonic 1, 2, 3, 1+2 or 1+2+3") if the mode
    is unrecognized. Returns the value from mode_orders directly without type
    coercion, preserving exact legacy return semantics when dynamically substituted.
    """
    if mode_orders is None:
        mode_orders = DEFAULT_HARMONIC_MODE_ORDERS
    value = str(mode).strip() if mode is not None else ""
    if value not in mode_orders:
        raise ValueError("Select harmonic 1, 2, 3, 1+2 or 1+2+3")
    return mode_orders[value]


def active_lockins_for_pass(
    schedules: Mapping[str, Sequence[int]],
    pass_index: int,
) -> tuple[str, ...]:
    """Return the lock-in keys scheduled to measure during pass_index (0-based).

    A lock-in drops out once its scheduled orders end. Keys are returned in the
    iteration order of schedules.
    """
    return tuple(k for k, orders in schedules.items() if pass_index < len(orders))


def schedule_harmonic_passes(
    settings: Mapping[str, Any],
    schedules: Mapping[str, Sequence[int]],
    validator: Callable[[dict[str, Any]], Any] | None = None,
    harmonic_setting_keys: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Generate per-pass transport scan settings for multi-pass harmonics.

    Each pass is a shallow copy of settings with updated:
      - 'harmonic_pass': 1-based pass index (1, 2, ...)
      - 'active_lockins': tuple of meter keys active in that pass
      - Harmonic setting keys (e.g. 'harmonic_a') updated for active meters

    Parameters
    ----------
    settings : Mapping[str, Any]
        Base transport scan settings dictionary.
    schedules : Mapping[str, Sequence[int]]
        Mapping of lock-in key to sequence of harmonic orders.
    validator : Callable[[dict[str, Any]], Any] | None
        Optional per-pass validation callable receiving the pass dictionary.
    harmonic_setting_keys : Mapping[str, str] | None
        Mapping of lock-in key to settings dict key (defaults to
        DEFAULT_SR830_HARMONIC_SETTING_KEYS).

    Returns
    -------
    list[dict[str, Any]]
        List of configuration dictionaries, one per pass.
    """
    if harmonic_setting_keys is None:
        harmonic_setting_keys = DEFAULT_SR830_HARMONIC_SETTING_KEYS

    pass_count = max((len(orders) for orders in schedules.values()), default=1)
    passes: list[dict[str, Any]] = []

    for index in range(pass_count):
        config = dict(settings, harmonic_pass=index + 1)
        config["active_lockins"] = active_lockins_for_pass(schedules, index)
        for key in config["active_lockins"]:
            config[harmonic_setting_keys[key]] = schedules[key][index]
        if validator is not None:
            validator(config)
        passes.append(config)

    return passes
