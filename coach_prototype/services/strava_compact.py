"""Strava stream adapter for :mod:`fit_compact` (no FIT parser required)."""
from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np

from services.fit_compact import (
    CURVE_DURATIONS,
    LLM_BEST,
    PAUSE_MIN_GAP,
    SCORE_REF,
    best_avg,
    level_of,
    r,
    regularize,
    select_segment,
    session_curve_best,
    summarize_session,
)

STREAM_TYPES = ['time', 'watts', 'heartrate', 'velocity_smooth', 'cadence', 'altitude']
MAPPING = {'p': 'watts', 'c': 'cadence', 'h': 'heartrate', 's': 'velocity_smooth', 'a': 'altitude'}


def fetch_streams(strava_client, strava_id):
    """Fetch 1-Hz/high-resolution streams in one Strava API call per activity."""
    return strava_client.get_activity_streams(
        strava_id,
        types=STREAM_TYPES,
        resolution='high',
    )


def _data(streams, key):
    stream = streams.get(key)
    if stream is None:
        return None
    values = getattr(stream, 'data', stream)
    return list(values) if values is not None else None


def streams_to_channels(streams):
    """Convert Strava streams to compressed active-second channels plus elapsed `tt`."""
    times = _data(streams, 'time')
    if times is None or len(times) < 10:
        raise ValueError("stream 'time' absent or too short")
    idx = np.round(np.asarray(times, dtype=float)).astype(int)
    raw = {}
    for channel, stream_name in MAPPING.items():
        values = _data(streams, stream_name)
        if values is not None and len(values) == len(idx):
            raw[channel] = np.asarray([np.nan if value is None else value for value in values], dtype=float)
        else:
            raw[channel] = np.full(len(idx), np.nan)
    return regularize(idx, raw)


def time_report(streams):
    """Describe timestamp continuity; retain pause/gap counters for diagnostics."""
    times = _data(streams, 'time')
    if times is None or len(times) < 2:
        raise ValueError("stream 'time' absent or too short")
    timestamps = np.round(np.asarray(times, dtype=float)).astype(int)
    gaps = np.diff(timestamps)
    channels = streams_to_channels(streams)
    pause_gaps = gaps[gaps >= PAUSE_MIN_GAP]
    return {
        'points': int(len(timestamps)),
        'elapsed_s': int(timestamps[-1] - timestamps[0] + 1),
        'ecarts': dict(Counter(np.minimum(gaps, 4).tolist()).most_common()),
        'sauts_2s': int((gaps == 2).sum()),
        f'pauses_>={PAUSE_MIN_GAP}s': int(len(pause_gaps)),
        'pause_count': int(len(pause_gaps)),
        'pause_total_s': int(channels['el'] - len(channels['p'])),
        'actif_s': int(len(channels['p'])),
        'monotone': bool(np.all(gaps > 0)),
        'channels_non_vides': {
            key: int(np.any(~np.isnan(np.asarray([np.nan if value is None else value
                                                  for value in (_data(streams, name) or [])], dtype=float)))
            for key, name in MAPPING.items()
        },
    }


def compact_from_streams(streams, start_dt, weight, ftp=None, hrmax=None, segment=None, compute_best=True):
    """Return a compact LLM session summary and best-effort record for level stats.

    `best_json` must be discarded by the caller unless Strava says device_watts.
    Segment cropping affects only the returned summary; power bests use the full ride.
    """
    channels = streams_to_channels(streams)
    _, meta = summarize_session(start_dt, channels, float(weight), ftp, hrmax)
    summary, _ = summarize_session(
        start_dt, select_segment(channels, segment), float(weight), ftp, hrmax
    )
    best = session_curve_best(channels, float(weight)) if compute_best and meta['has_power'] else None
    return summary, best


def level_snapshot(rows, weight, today=None, window_days=90):
    """Compact current level and prior-period trend from activity best_json rows."""
    return level_of(rows, weight, today=today, window_days=window_days)


def downsample_streams(streams, limit=300):
    """Downsample the already-fetched stream object for graphs; never issue another API call."""
    times = _data(streams, 'time')
    if not times:
        return {}
    count = len(times)
    if count <= limit:
        indices = list(range(count))
    else:
        indices = np.linspace(0, count - 1, num=limit, dtype=int).tolist()
    result = {}
    for name in STREAM_TYPES:
        values = _data(streams, name)
        if values is not None and len(values) == count:
            result[name] = [values[index] for index in indices]
    if 'time' in result:
        result['time_min'] = [round(float(value) / 60, 2) for value in result['time']]
    return result
