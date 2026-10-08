"""Compact one-activity physiology summary shared by FIT/Strava stream inputs.

FIT parsing and filesystem/archive CLI are deliberately omitted: this service
uses the exact active-second/time-axis calculations needed by Strava streams.
"""
from datetime import datetime, timezone
import numpy as np

CURVE_DURATIONS = [
    (5, '5s'), (10, '10s'), (15, '15s'), (30, '30s'), (45, '45s'),
    (60, '1min'), (120, '2min'), (300, '5min'), (600, '10min'),
    (900, '15min'), (1200, '20min'), (1800, '30min'),
    (2700, '45min'), (3600, '60min'),
]
LLM_BEST = ['5s', '30s', '1min', '5min', '20min', '60min']
SCORE_REF = {
    'sprint': ('5s', 5.0, 20.0),
    'anaerobie': ('1min', 3.0, 9.0),
    'vo2': ('5min', 2.5, 6.5),
    'seuil': ('20min', 2.0, 5.5),
    'endurance': ('60min', 1.5, 4.5),
}
LEGEND = (
    'FIT compact v1. crop=[début_s,durée_s] si recadré. d=date UTC, t=durée chrono active min, '
    'pz=pauses min, mv=min en mouvement, km, dp=D+ m, kg. w=[moy,NP,max] W; hr=[moy,max] bpm; '
    'cad=moy rpm hors 0; v=vitesse moy km/h; if=intensity factor, tss, ftp W; '
    'best={durée:[W,W/kg]}; zp=minutes Z1..Z7; zh=minutes Z1..Z5; ef=efforts intenses; '
    'tl={s:pas sec, w:[W], hr:[bpm]}; dec=dérive puissance/FC %; cur=curseur cardio 0..1.'
)
FFILL_LIMIT = {'p': 3, 'c': 3, 's': 3, 'h': 10, 'a': 10}
PAUSE_MIN_GAP = 3


def ffill(values, limit, seg_start=None):
    """Forward-fill at most limit seconds and never across a pause."""
    values = np.asarray(values, dtype=float)
    pos = np.arange(len(values))
    idx = np.where(~np.isnan(values), pos, 0)
    np.maximum.accumulate(idx, out=idx)
    filled = values[idx].copy()
    bad = (pos - idx) > limit
    if seg_start is not None:
        bad |= idx < seg_start
    filled[bad] = np.nan
    return filled


def regularize(idx, raw):
    """Canonical compressed active-second channels plus real elapsed `tt`.

    Duplicates keep the last record; isolated 2-second gaps interpolate one
    active second. Gaps >=3 seconds are paused clock time: they are excluded
    from channel samples, never zero-filled, and remain visible in `tt`/`el`.
    """
    idx = np.asarray(idx, dtype=int)
    if idx.ndim != 1 or len(idx) < 2:
        raise ValueError('at least two timestamps are required')
    keep = np.append(np.diff(idx) > 0, True)
    idx = idx[keep]
    if len(idx) < 2 or np.any(np.diff(idx) <= 0):
        raise ValueError('timestamps must be strictly increasing after deduplication')
    raw = {key: np.asarray(values, dtype=float)[keep] for key, values in raw.items()}
    idx = idx - idx[0]
    elapsed = int(idx[-1]) + 1
    active = np.zeros(elapsed, dtype=bool)
    active[idx] = True
    for i in np.flatnonzero(np.diff(idx) == 2):
        active[idx[i] + 1] = True
    positions = np.arange(elapsed)
    run_start = active & ~np.concatenate(([False], active[:-1]))
    segment_start = np.where(run_start, positions, 0)
    np.maximum.accumulate(segment_start, out=segment_start)

    out = {}
    for key, values in raw.items():
        channel = np.full(elapsed, np.nan)
        channel[idx] = values
        out[key] = ffill(channel, FFILL_LIMIT[key], segment_start)[active]
    out['p'] = np.clip(np.nan_to_num(out.get('p', np.full(active.sum(), np.nan))), 0, None)
    out['c'] = np.clip(np.nan_to_num(out.get('c', np.full(active.sum(), np.nan))), 0, None)
    out['s'] = np.clip(np.nan_to_num(out.get('s', np.full(active.sum(), np.nan))) * 3.6, 0, None)
    out['tt'] = positions[active]
    out['el'] = elapsed
    return out


def best_avg(values, window, tt=None):
    n = len(values)
    if n < window:
        return None
    sums = np.cumsum(np.insert(np.nan_to_num(values), 0, 0.0))
    averages = (sums[window:] - sums[:-window]) / window
    if tt is not None:
        contiguous = (tt[window - 1:] - tt[:n - window + 1]) == window - 1
        averages = averages[contiguous]
        if not len(averages):
            return None
    return float(averages.max())


def np_power(power, tt=None):
    if len(power) < 30:
        return float(power.mean()) if len(power) else 0.0
    sums = np.cumsum(np.insert(power, 0, 0.0))
    rolling = (sums[30:] - sums[:-30]) / 30
    if tt is not None:
        contiguous = (tt[29:] - tt[:len(power) - 29]) == 29
        if contiguous.any():
            rolling = rolling[contiguous]
    return float(np.mean(rolling ** 4) ** 0.25) if len(rolling) else 0.0


def estimate_ftp(power, tt=None):
    p60, p20, p5 = best_avg(power, 3600, tt), best_avg(power, 1200, tt), best_avg(power, 300, tt)
    if p60 and p60 > 10:
        return round(p60, 1)
    if p20 and p20 > 10:
        return round(p20 * .95, 1)
    if p5 and p5 > 10:
        return round(p5 * .75, 1)
    return None


def cardio_cursor(heart_rate):
    values = heart_rate[~np.isnan(heart_rate)]
    values = values[values > 30]
    if len(values) < 30:
        return None
    maximum = np.percentile(values, 99)
    zone_percent = float(np.mean(values > maximum * .85) * 100)
    rises = np.diff(values)
    rises = rises[rises > 0]
    acceleration = float(np.mean(rises) * 60) if len(rises) else 0.0
    a = float(np.clip((acceleration - 5) / 35, 0, 1))
    z = float(np.clip((zone_percent - 20) / 50, 0, 1))
    return round(.6 * a + .4 * z, 3)


def find_efforts(values, threshold, tt, min_len=30, merge_gap=20, top=8):
    smooth = np.convolve(np.nan_to_num(values), np.ones(15) / 15, mode='same')
    edges = np.diff(np.concatenate(([0], (smooth >= threshold).astype(int), [0])))
    runs = []
    for start, end in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        cuts = [start] + [int(b) + start + 1 for b in np.flatnonzero(np.diff(tt[start:end]) > 1)] + [end]
        runs += [[a, b] for a, b in zip(cuts[:-1], cuts[1:])]
    merged = []
    for a, b in runs:
        if merged and tt[a] - tt[merged[-1][1] - 1] - 1 <= merge_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [run for run in merged if run[1] - run[0] >= min_len]
    merged.sort(key=lambda run: -np.nansum(values[run[0]:run[1]]))
    return sorted(merged[:top])


def bucket_mean(values, tt, step):
    count_bins = int(tt[-1] // step) + 1
    buckets = (tt // step).astype(int)
    valid = ~np.isnan(values)
    counts = np.bincount(buckets[valid], minlength=count_bins)
    totals = np.bincount(buckets[valid], weights=values[valid], minlength=count_bins)
    return [r(totals[i] / counts[i]) if counts[i] else None for i in range(count_bins)]


def mean_or_none(values):
    values = values[~np.isnan(values)] if values.dtype.kind == 'f' else values
    return float(values.mean()) if len(values) else None


def r(value, nd=0):
    if value is None:
        return None
    result = round(float(value), nd)
    return int(result) if nd == 0 else result


def segments(ch, min_len=60):
    tt = ch['tt']
    cuts = np.concatenate(([0], np.flatnonzero(np.diff(tt) > 1) + 1, [len(tt)]))
    return [(int(a), int(b)) for a, b in zip(cuts[:-1], cuts[1:]) if b - a >= min_len]


def select_segment(ch, mode):
    if not mode:
        return ch
    tt = ch['tt']
    if mode == 'longest':
        found = segments(ch, 1)
        if not found:
            raise ValueError('no active segment available')
        start, end = max(found, key=lambda pair: pair[1] - pair[0])
    else:
        lo, hi = (float(value) for value in str(mode).split('-'))
        start, end = int(np.searchsorted(tt, lo)), int(np.searchsorted(tt, hi))
    if end - start < 30:
        raise ValueError(f"segment '{mode}' empty or too short")
    out = {key: ch[key][start:end] for key in ('p', 'c', 'h', 's', 'a')}
    origin = int(tt[start])
    out['tt'] = tt[start:end] - origin
    out['el'] = int(out['tt'][-1]) + 1
    out['crop'] = [origin, int(end - start)]
    return out


def summarize_session(start_dt, ch, weight, ftp=None, hrmax=None):
    """Create minified one-session dictionary; `tt` prevents windows crossing pauses."""
    p, c, h, speed, altitude, tt = ch['p'], ch['c'], ch['h'], ch['s'], ch['a'], ch['tt']
    active_seconds = len(p)
    has_power, has_hr = bool(np.any(p > 0)), bool(np.any(h > 30))
    moving = speed > 1.0
    ftp = ftp or (estimate_ftp(p, tt) if has_power else None)
    hrmax = hrmax or (float(np.nanpercentile(h[h > 30], 99)) if has_hr else None)
    if isinstance(start_dt, datetime):
        dt = start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=timezone.utc)
        timestamp = dt.timestamp()
    else:
        timestamp = float(start_dt)
    out = {'fv': 1, 'd': datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%d'),
           't': r(active_seconds / 60), 'mv': r(moving.sum() / 60), 'kg': float(weight),
           'km': r(speed.sum() / 3600, 1)}
    if 'crop' in ch:
        out['crop'] = ch['crop']
    pause_min = (ch['el'] - active_seconds) / 60
    if pause_min >= .5:
        out['pz'] = r(pause_min)
    if len(altitude) and np.any(~np.isnan(altitude)):
        values = altitude[~np.isnan(altitude)]
        width = min(10, len(values))
        smooth = np.convolve(values, np.ones(width) / width, mode='valid')
        out['dp'] = r(np.clip(np.diff(smooth), 0, None).sum())
    if moving.any():
        out['v'] = r(speed[moving].mean(), 1)
    if has_power:
        normalized = np_power(p, tt)
        out['w'] = [r(p.mean()), r(normalized), r(p.max())]
        if ftp:
            intensity = normalized / ftp
            out.update({'ftp': r(ftp), 'if': r(intensity, 2),
                        'tss': r(active_seconds * normalized * intensity / (ftp * 3600) * 100)})
            zones = np.digitize(p, np.array([.55, .75, .90, 1.05, 1.20, 1.50]) * ftp)
            out['zp'] = [r(value, 1) for value in np.bincount(zones, minlength=7) / 60]
        best = {}
        for seconds, label in CURVE_DURATIONS:
            if label in LLM_BEST:
                value = best_avg(p, seconds, tt)
                if value:
                    best[label] = [r(value), r(value / weight, 2)]
        out['best'] = best
    cadence = c[c > 0]
    if len(cadence):
        out['cad'] = r(cadence.mean())
    if has_hr:
        valid_hr = h[~np.isnan(h)]
        out['hr'] = [r(valid_hr.mean()), r(valid_hr.max())]
        zones = np.digitize(valid_hr, np.array([.60, .70, .80, .90]) * hrmax)
        out['zh'] = [r(value, 1) for value in np.bincount(zones, minlength=5) / 60]
        cursor = cardio_cursor(h)
        if cursor is not None:
            out['cur'] = cursor
    if has_power and ftp:
        runs = find_efforts(p, .90 * ftp, tt)
    elif has_hr:
        runs = find_efforts(np.nan_to_num(h), .85 * hrmax, tt)
    else:
        runs = []
    if runs:
        out['ef'] = [[int(tt[a]), int(b-a), r(p[a:b].mean()), r(mean_or_none(h[a:b])),
                      r(c[a:b][c[a:b] > 0].mean()) if np.any(c[a:b] > 0) else None] for a,b in runs]
    timeline = {'s': 300}
    if has_power:
        timeline['w'] = bucket_mean(p, tt, 300)
    if has_hr:
        timeline['hr'] = bucket_mean(h, tt, 300)
    out['tl'] = timeline
    if has_power and has_hr and active_seconds >= 2400:
        half = active_seconds // 2
        first = p[:half].mean() / max(np.nanmean(h[:half]), 1)
        second = p[half:].mean() / max(np.nanmean(h[half:]), 1)
        out['dec'] = r((first - second) / first * 100, 1)
    meta = {'has_power': has_power, 'has_cadence': bool(len(cadence)),
            'has_heart_rate': has_hr, 'has_speed': bool(moving.any())}
    return out, meta


def session_curve_best(ch, weight):
    """Best durations for a power-meter activity, based on the entire activity."""
    best = {}
    for seconds, label in CURVE_DURATIONS:
        value = best_avg(ch['p'], seconds, ch['tt'])
        if value:
            best[label] = round(value, 1)
    return {'kg': float(weight), 'p': best}


def level_of(rows, weight, today=None, window_days=90):
    """Build compact 90-day current level and prior-90-day trend from (date,best_json)."""
    from datetime import date as date_type, timedelta
    today = today or datetime.now(timezone.utc).date()
    current, previous = {}, {}
    for date_value, best_json in rows:
        day = date_value.date() if isinstance(date_value, datetime) else date_value
        if not isinstance(day, date_type) or not isinstance(best_json, dict):
            continue
        target = current if today - timedelta(days=window_days) <= day <= today else previous if today - timedelta(days=2*window_days) <= day < today - timedelta(days=window_days) else None
        if target is None:
            continue
        kilograms = best_json.get('kg') or weight or 0
        if kilograms <= 0:
            continue
        for label, watts in (best_json.get('p') or {}).items():
            try:
                value = float(watts) / float(kilograms)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            target[label] = max(target.get(label, 0.0), value)
    def scores(best):
        result = {}
        for name, (label, low, high) in SCORE_REF.items():
            if label in best:
                result[name] = int(round(float(np.clip((best[label]-low)/(high-low), 0, 1))*100))
        level = int(round(sum(result.values())/len(result))) if result else None
        return result, level
    current_scores, current_level = scores(current)
    _, previous_level = scores(previous)
    ftp_wkg = max(current.get('60min', 0), .95*current.get('20min', 0))
    return {'v': 1, 'asof': today.isoformat(), 'kg': float(weight) if weight else None,
            'ftp': r(ftp_wkg * float(weight)) if ftp_wkg and weight else None,
            'ftp_wkg': r(ftp_wkg, 2) if ftp_wkg else None,
            'pc': {label: r(current[label], 2) for _, label in CURVE_DURATIONS if label in LLM_BEST and label in current},
            'sc': current_scores, 'lvl': current_level,
            'tr': (current_level - previous_level) if current_level is not None and previous_level is not None else None}
