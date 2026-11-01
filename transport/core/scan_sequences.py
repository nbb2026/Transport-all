"""Hardware-independent endpoint-inclusive scan sequence calculations.

The implementation is moved verbatim from Transport_all.py. Physical limits
and units remain the responsibility of callers in that application.
"""

import math


def build_round_trip_values(
    start: float,
    end: float,
    step: float,
    *,
    decimals: int,
    max_total_points: int = 100_000,
    too_many_message: str = "Total scan points exceed 100000; please increase the step",
) -> list[float]:
    """Build one endpoint-inclusive start→end→start numeric cycle.

    All voltage/current/field scans use this one implementation so endpoint,
    descending-scan and non-divisible-step behaviour cannot drift apart.  The
    point count is calculated before allocation, which also rejects an
    accidentally tiny step immediately instead of running a 100000-iteration
    Python loop first.

    Callers retain responsibility for physical units and hardware limits.
    """
    start = float(start)
    end = float(end)
    step = abs(float(step))
    if not all(math.isfinite(value) for value in (start, end, step)):
        raise ValueError("Scan start, end and step must be finite values")
    if step <= 0.0:
        raise ValueError("Scan step must be greater than 0")
    max_total_points = int(max_total_points)
    if max_total_points < 1:
        raise ValueError("Maximum scan point count must be greater than 0")
    if start == end:
        return [float(round(start, int(decimals)))]

    ratio = abs(end - start) / step
    if not math.isfinite(ratio):
        raise ValueError(too_many_message)
    nearest = round(ratio)
    if math.isclose(ratio, nearest, rel_tol=1e-12, abs_tol=1e-12):
        interval_count = max(1, int(nearest))
    else:
        interval_count = max(1, int(math.ceil(ratio)))
    one_way_points = interval_count + 1
    cycle_points = 2 * one_way_points - 1
    if cycle_points > max_total_points:
        raise ValueError(too_many_message)

    direction = 1.0 if end > start else -1.0
    # The last regular step can never replace the exact requested endpoint.
    # Keeping the endpoint explicit prevents a non-divisible step from
    # overshooting the requested hardware setpoint.
    outward = [
        round(start + direction * step * index, int(decimals))
        for index in range(interval_count)
    ]
    endpoint = round(end, int(decimals))
    if not outward or outward[-1] != endpoint:
        outward.append(endpoint)
    cycle = outward + outward[-2::-1]
    if len(cycle) > max_total_points:
        raise ValueError(too_many_message)
    return [float(value) for value in cycle]


def ppms_scan_axis(start, end, step):
    start, end, step = float(start), float(end), abs(float(step))
    if not all(math.isfinite(v) for v in (start, end, step)) or step <= 0:
        raise ValueError("Scan range must be finite and the step must be greater than 0")
    # 1e-9: (0.4 - 0.1) / 0.1 is 3.0000000000000004, which repeated the end.
    count = int(math.ceil(abs(end-start)/step - 1e-9))
    if count > 10000:
        raise ValueError("A single-axis scan allows at most 10001 points")
    direction = 1 if end >= start else -1
    return tuple(start + direction*step*i for i in range(count)) + (end,)


def lakeshore_ramp_seconds(currents, rate_a_s) -> float:
    """The ramping time of the setpoints ``currents`` (A), in order, at
    ``rate_a_s``: sum |dI| / rate.  The Yes/No time estimates add it."""
    values = [float(value) for value in currents]
    rate = float(rate_a_s)
    if not math.isfinite(rate) or rate <= 0 or len(values) < 2:
        return 0.0
    return sum(abs(b - a) for a, b in zip(values, values[1:])) / rate


