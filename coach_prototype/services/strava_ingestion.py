"""Incremental per-user Strava activity import and compact preprocessing."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import Activity, LevelSnapshotCache, StravaConnection, User
from services.compact_ingestion import process_activity_streams
from services.strava_api import StravaAPIClient, StravaAPIError

logger = logging.getLogger(__name__)
INITIAL_ACTIVITY_COUNT = 20
PAGE_SIZE = 100
MAX_INCREMENTAL_ACTIVITIES = 500


def _strava_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fetch_activity_summaries(client: StravaAPIClient, last_sync: datetime | None):
    """Fetch last 20 on initial link, then pages strictly newer than sync cursor."""
    if last_sync is None:
        return client.list_activities(per_page=INITIAL_ACTIVITY_COUNT, page=1), True
    cursor = last_sync.replace(tzinfo=timezone.utc) if last_sync.tzinfo is None else last_sync
    after = max(0, int(cursor.timestamp()))
    results = []
    max_pages = (MAX_INCREMENTAL_ACTIVITIES + PAGE_SIZE - 1) // PAGE_SIZE
    for page in range(1, max_pages + 1):
        batch = client.list_activities(per_page=PAGE_SIZE, page=page, after=after)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < PAGE_SIZE or len(results) >= MAX_INCREMENTAL_ACTIVITIES:
            break
    return results[:MAX_INCREMENTAL_ACTIVITIES], False


def import_activity(db: Session, athlete: User, client: StravaAPIClient, payload: dict):
    """Persist one activity and process its one high-resolution stream response."""
    external_id = payload.get('id')
    start = _strava_datetime(payload.get('start_date'))
    if external_id is None or start is None:
        raise ValueError('Strava activity is missing id/start_date')
    external_id = int(external_id)
    activity = db.scalar(select(Activity).where(Activity.source_id == external_id))
    if activity is not None:
        if activity.user_id != athlete.id:
            raise StravaAPIError('Strava activity identifier is already owned by another Coach user')
        # A previous stream failure can be retried during a later incremental pass.
        if activity.compact_json is not None or athlete.weight_kg is None:
            return activity, False, False
    else:
        moving_seconds = int(payload.get('moving_time') or 0)
        distance_m = _number(payload.get('distance'))
        activity = Activity(
            user_id=athlete.id,
            source_id=external_id,
            title=str(payload.get('name') or 'Strava activity')[:255],
            occurred_at=start,
            sport=str(payload.get('sport_type') or 'Ride')[:50],
            duration_minutes=round(moving_seconds / 60) if moving_seconds else None,
            moving_time_s=moving_seconds or None,
            elapsed_time_s=int(payload.get('elapsed_time') or 0) or None,
            distance_km=round(distance_m / 1000, 2) if distance_m is not None else None,
            elevation_gain_m=_number(payload.get('total_elevation_gain')),
            avg_watts=round(_number(payload.get('average_watts'))) if payload.get('average_watts') is not None else None,
            avg_heartrate=round(_number(payload.get('average_heartrate'))) if payload.get('average_heartrate') is not None else None,
            avg_cadence=round(_number(payload.get('average_cadence'))) if payload.get('average_cadence') is not None else None,
            device_watts=bool(payload.get('device_watts')) if payload.get('device_watts') is not None else None,
            notes=str(payload.get('description') or '')[:5000] or None,
        )
        db.add(activity)
        db.flush()

    if athlete.weight_kg is None or float(athlete.weight_kg) <= 0:
        # Keep the activity row; compact W/kg and level curves require a real weight.
        return activity, True, False
    try:
        summary, report = process_activity_streams(activity, athlete, client)
        compact_chars = len(__import__('json').dumps(summary, ensure_ascii=False, separators=(',', ':'))) if summary else 0
        if summary:
            logger.info('Compact activity id=%s chars=%s time_report=%s', external_id, compact_chars, report)
        return activity, True, summary is not None
    except Exception as exc:
        # Preserve summary metadata so the user can see the activity; compact can be retried on demand.
        logger.warning('Compact processing failed for Strava activity id=%s: %s', external_id, type(exc).__name__)
        return activity, True, False


def sync_activities(db: Session, user_id: int, client: StravaAPIClient):
    athlete = db.get(User, user_id)
    if athlete is None:
        raise ValueError('Coach user not found')
    connection = db.scalar(select(StravaConnection).where(StravaConnection.user_id == user_id).with_for_update())
    if connection is None:
        raise ValueError('Strava account is not connected')
    summaries, initial = fetch_activity_summaries(client, connection.last_activity_sync_at)
    added = already_present = compacted = compact_pending = 0
    errors = []
    for payload in summaries:
        external_id = payload.get('id')
        if external_id is None:
            continue
        existing = db.scalar(select(Activity).where(Activity.source_id == int(external_id)))
        if existing is not None and existing.user_id != user_id:
            errors.append({'strava_id': int(external_id), 'error': 'activity-owned-by-another-user'})
            continue
        if existing is not None and existing.compact_json is not None:
            already_present += 1
            continue
        try:
            _, inserted, has_compact = import_activity(db, athlete, client, payload)
            added += int(inserted)
            already_present += int(not inserted)
            compacted += int(has_compact)
            compact_pending += int(not has_compact)
        except Exception as exc:
            errors.append({'strava_id': int(external_id), 'error': type(exc).__name__})
            logger.warning('Activity import failed strava_id=%s error=%s', external_id, type(exc).__name__)
    connection.last_activity_sync_at = datetime.now(timezone.utc)
    cache = db.get(LevelSnapshotCache, user_id)
    if cache is not None:
        db.delete(cache)
    db.commit()
    return {
        'status': 'ok', 'mode': 'initial' if initial else 'incremental',
        'fetched': len(summaries), 'imported': added, 'already_present': already_present,
        'compacted': compacted, 'compact_pending_weight_or_streams': compact_pending,
        'errors': errors,
    }
