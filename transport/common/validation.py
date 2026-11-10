"""Pure validation calculations for Keithley 6221 and SR830 transport settings."""

from __future__ import annotations

import math
from typing import Any, Sequence

DEFAULT_K6221_MAX_ABS_CURRENT_A: float = 0.105
DEFAULT_K6221_MIN_COMPLIANCE_V: float = 0.1
DEFAULT_K6221_MAX_COMPLIANCE_V: float = 105.0
DEFAULT_K6221_MIN_FREQUENCY_HZ: float = 1e-3
DEFAULT_K6221_MAX_FREQUENCY_HZ: float = 1e5
DEFAULT_SR830_KEYS: tuple[str, ...] = ("830_a", "830_b", "830_c")
DEFAULT_SR830_LABELS: dict[str, str] = {
    "830_a": "A",
    "830_b": "B",
    "830_c": "C",
}
DEFAULT_SR830_MIN_HARMONIC: int = 1
DEFAULT_SR830_MAX_HARMONIC: int = 19999
DEFAULT_SR830_MAX_DEMOD_FREQ_HZ: float = 102000.0


def validate_transport_scan_settings(
    current_rms_ma: float,
    frequency_hz: float,
    compliance_v: float,
    harmonic_a: int,
    harmonic_b: int,
    active_lockins: tuple[str, ...] = ("830_a", "830_b"),
    allow_no_lockins: bool = False,
    harmonic_c: int = 1,
    *,
    max_abs_current_a: float = DEFAULT_K6221_MAX_ABS_CURRENT_A,
    min_compliance_v: float = DEFAULT_K6221_MIN_COMPLIANCE_V,
    max_compliance_v: float = DEFAULT_K6221_MAX_COMPLIANCE_V,
    valid_sr830_keys: Sequence[str] = DEFAULT_SR830_KEYS,
) -> dict[str, Any]:
    """Validate 6221/SR830 settings used by transport scans.

    Coerces numeric inputs, validates physical and demodulation limits,
    and derives the 6221 peak current amplitude (peak_a in Amperes).
    """
    current_rms_ma = float(current_rms_ma)
    frequency_hz = float(frequency_hz)
    compliance_v = float(compliance_v)
    harmonic_a = int(harmonic_a)
    harmonic_b = int(harmonic_b)
    harmonic_c = int(harmonic_c)
    active_lockins = tuple(str(key) for key in active_lockins)

    if not active_lockins and not allow_no_lockins:
        raise ValueError("PPMS field sweep requires at least one connected SR830")
    if any(key not in valid_sr830_keys for key in active_lockins):
        raise ValueError("PPMS SR830 slot is invalid")
    if not all(
        math.isfinite(value)
        for value in (current_rms_ma, frequency_hz, compliance_v)
    ):
        raise ValueError("6221 parameters for the PPMS transport scan must be finite values")
    if current_rms_ma <= 0:
        raise ValueError("6221 AC current for the PPMS transport scan must be greater than 0 mA RMS")

    peak_a = math.sqrt(2.0) * current_rms_ma * 1e-3
    if peak_a > max_abs_current_a:
        maximum_rms_ma = max_abs_current_a / math.sqrt(2.0) * 1000.0
        raise ValueError(
            f"6221 sine-wave peak must not exceed {max_abs_current_a * 1000:g} mA; "
            f"the GUI RMS current limit is about {maximum_rms_ma:.6g} mA"
        )
    if not 1e-3 <= frequency_hz <= 1e5:
        raise ValueError("6221 waveform frequency must be within 0.001–100000 Hz")
    if not min_compliance_v <= compliance_v <= max_compliance_v:
        raise ValueError(
            f"6221 compliance voltage must be within {min_compliance_v:g}–"
            f"{max_compliance_v:g} V"
        )

    harmonics = {"830_a": harmonic_a, "830_b": harmonic_b, "830_c": harmonic_c}
    for key in active_lockins:
        label = DEFAULT_SR830_LABELS[key]
        harmonic = harmonics[key]
        if not 1 <= harmonic <= 19999:
            raise ValueError(f"SR830 slot {label} harmonic must be within 1–19999")
        if frequency_hz * harmonic > 102000.0:
            raise ValueError(f"SR830 slot {label} demodulation frequency must not exceed 102 kHz")

    return {
        "current_rms_ma": current_rms_ma,
        "frequency_hz": frequency_hz,
        "compliance_v": compliance_v,
        "harmonic_a": harmonic_a,
        "harmonic_b": harmonic_b,
        "harmonic_c": harmonic_c,
        "active_lockins": active_lockins,
        "allow_no_lockins": allow_no_lockins,
        "peak_a": peak_a,
    }
