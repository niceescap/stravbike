"""One-fetch compact processing and diagnostics for one Strava activity."""
import logging

from services.strava_compact import compact_from_streams, downsample_streams, fetch_streams, time_report

logger = logging.getLogger(__name__)


def process_activity_streams(activity, athlete, strava_client, *, segment=None):
    """Fetch high-resolution once; derive compact JSON and graph streams from that object.

    Returns (summary, diagnostics). `best_json` is stored only for an activity
    Strava marks as device_watts. A selected segment changes only the returned
    summary; curve bests are calculated across the complete activity.
    """
    if not activity.source_id:
        raise ValueError('Activity has no Strava source id')
    streams = fetch_streams(strava_client, activity.source_id)
    report = time_report(streams)
    logger.info('Strava stream time report activity=%s: %s', activity.source_id, report)
    if (report['pause_count'] == 0 and activity.elapsed_time_s is not None
            and activity.moving_time_s is not None
            and activity.elapsed_time_s - activity.moving_time_s > 120):
        logger.warning(
            'Strava time stream has no >=%ds pause gaps for activity=%s, while elapsed-moving=%ds; '
            'time stream may be pause-compressed; moving stream may be needed for race crop.',
            3, activity.source_id, activity.elapsed_time_s - activity.moving_time_s,
        )

    # Reuse the same high-resolution response for chart storage. Never fetch a
    # second stream object for compact summary or best values.
    activity.streams_json = downsample_streams(streams)
    weight = float(athlete.weight_kg) if athlete.weight_kg is not None else None
    if not weight or weight <= 0:
        activity.compact_json = None
        activity.best_json = None
        return None, report

    ftp = int(athlete.ftp_watts) if athlete.ftp_watts is not None and athlete.ftp_watts > 0 else None
    hrmax = int(athlete.max_heartrate) if athlete.max_heartrate is not None and athlete.max_heartrate > 0 else None
    summary, full_activity_best = compact_from_streams(
        streams,
        activity.occurred_at,
        weight,
        ftp=ftp,
        hrmax=hrmax,
        segment=segment,
    )
    # Persist the full-session summary on ordinary processing. Race-segment
    # requests return a crop but never replace the stored whole-activity JSON.
    if segment is None:
        activity.compact_json = summary
    activity.best_json = full_activity_best if activity.device_watts is True else None
    return summary, report
