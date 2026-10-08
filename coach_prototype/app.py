"""Isolated cycling-coach prototype. No Strava or inference traffic in demo mode."""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from email_validator import EmailNotValidError, validate_email

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', '')
SESSION_SECRET = os.getenv('SESSION_SECRET', '')
DEMO_MODE = os.getenv('DEMO_MODE') == '1'
ALLOW_SIGNUP = os.getenv('ALLOW_SIGNUP', '0') == '1'
COOKIE = 'coach_session'
SESSION_SECONDS = 8 * 3600

if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL must point to an isolated coach database')
if os.getenv('TESTING') != '1' and (
    not DATABASE_URL.startswith('postgresql') or make_url(DATABASE_URL).database != 'coach_proto'
):
    raise RuntimeError('Demo may only use the dedicated PostgreSQL coach_proto database')
if len(SESSION_SECRET) < 32:
    raise RuntimeError('SESSION_SECRET must be at least 32 characters')
if not DEMO_MODE:
    raise RuntimeError('This prototype may only run with DEMO_MODE=1')
logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'coach_users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    ftp_watts: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2))
    max_heartrate: Mapped[int | None] = mapped_column(Integer)
    credit_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model_choice: Mapped[str] = mapped_column(String(100), default='demo')


class Activity(Base):
    __tablename__ = 'coach_activities'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sport: Mapped[str] = mapped_column(String(50), default='Ride')
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2))
    avg_watts: Mapped[int | None] = mapped_column(Integer)
    avg_heartrate: Mapped[int | None] = mapped_column(Integer)
    avg_cadence: Mapped[int | None] = mapped_column(Integer)
    elevation_gain_m: Mapped[float | None] = mapped_column(Numeric(9, 2))
    moving_time_s: Mapped[int | None] = mapped_column(Integer)
    elapsed_time_s: Mapped[int | None] = mapped_column(Integer)
    device_watts: Mapped[bool | None] = mapped_column(Boolean)
    streams_json: Mapped[dict | None] = mapped_column(JSON)
    compact_json: Mapped[dict | None] = mapped_column(JSON)
    best_json: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)


class Artifact(Base):
    __tablename__ = 'coach_artifacts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    category: Mapped[str] = mapped_column(String(40), default='recommendation')
    markdown: Mapped[str] = mapped_column(Text)
    related_activity_id: Mapped[int | None] = mapped_column(ForeignKey('coach_activities.id'), nullable=True)


class StravaConnection(Base):
    """Encrypted, per-user Strava refresh-token connection."""
    __tablename__ = 'coach_strava_connections'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id'), unique=True, index=True)
    strava_athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    athlete_name: Mapped[str] = mapped_column(String(160))
    profile_pic_url: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(Text)
    last_activity_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OAuthState(Base):
    """Single-use OAuth CSRF state bound to a logged-in local user."""
    __tablename__ = 'coach_oauth_states'
    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LevelSnapshotCache(Base):
    __tablename__ = 'coach_level_cache'
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id', ondelete='CASCADE'), primary_key=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    source_signature: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LevelSnapshotCache(Base):
    __tablename__ = 'coach_level_cache'
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id', ondelete='CASCADE'), primary_key=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    source_signature: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310_000)
    return f'pbkdf2_sha256${salt}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        method, salt, digest = stored.split('$')
        if method != 'pbkdf2_sha256':
            return False
        return hmac.compare_digest(hash_password(password, salt).split('$')[-1], digest)
    except (ValueError, TypeError):
        return False


def sign_session(user_id: int) -> str:
    expiry = int(time.time()) + SESSION_SECONDS
    payload = f'{user_id}:{expiry}'
    sig = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}:{sig}'


def verify_session(cookie: str | None) -> int | None:
    try:
        if not cookie:
            return None
        uid, expiry, signature = cookie.split(':')
        payload = f'{uid}:{expiry}'
        expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if int(expiry) < int(time.time()) or not hmac.compare_digest(signature, expected):
            return None
        return int(uid)
    except (ValueError, TypeError):
        return None


def initialize_schema() -> None:
    """Create only Coach tables in the explicitly isolated coach_proto database."""
    Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_schema()
    yield


app = FastAPI(title='Coach prototype (demo only)', lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
templates = Jinja2Templates(directory=ROOT/'templates')


@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.url.path == '/app':
        return RedirectResponse('/login', status_code=303)
    return JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)


def get_db():
    with SessionLocal() as db:
        yield db


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = verify_session(request.cookies.get(COOKIE))
    user = db.get(User, uid) if uid is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail='Login required')
    return user


@app.get('/health')
def health():
    return {'status': 'demo'}


@app.get('/')
def root(request: Request):
    return RedirectResponse('/app' if verify_session(request.cookies.get(COOKIE)) else '/login', status_code=303)


# Bootstrap registration is explicitly enabled only for the first real account.
_signup_attempts: dict[str, list[float]] = {}


def _signup_response(request: Request, error: str, csrf_token: str, status_code: int = 400):
    response = templates.TemplateResponse(request, 'signup.html', {'error': error, 'csrf_token': csrf_token}, status_code=status_code)
    response.set_cookie('coach_signup_csrf', csrf_token, max_age=600, httponly=True,
                        secure=True, samesite='strict', path='/signup')
    return response


@app.get('/signup', response_class=HTMLResponse)
def signup_page(request: Request):
    if not ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail='Account creation is closed')
    csrf_token = secrets.token_urlsafe(32)
    return _signup_response(request, '', csrf_token, status_code=200)


@app.post('/signup', response_class=HTMLResponse)
def signup(
    request: Request,
    csrf_token: Annotated[str, Form()],
    email: Annotated[str, Form()],
    name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirm: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    if not ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail='Account creation is closed')
    stored_csrf = request.cookies.get('coach_signup_csrf', '')
    if not stored_csrf or not secrets.compare_digest(stored_csrf, csrf_token):
        return _signup_response(request, 'Formulaire expiré. Rechargez la page et réessayez.', secrets.token_urlsafe(32), 403)

    address = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    recent = [t for t in _signup_attempts.get(address, []) if now - t < 600]
    if len(recent) >= 5:
        return _signup_response(request, 'Trop de tentatives de création. Réessayez dans 10 minutes.', csrf_token, 429)
    _signup_attempts[address] = recent + [now]

    display_name = ' '.join(name.split())
    try:
        normalized_email = validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return _signup_response(request, 'Saisissez une adresse email valide.', csrf_token, 400)
    if not display_name or len(display_name) > 120:
        return _signup_response(request, 'Le nom doit contenir entre 1 et 120 caractères.', csrf_token, 400)
    if len(password) < 12 or len(password) > 128:
        return _signup_response(request, 'Choisissez un mot de passe de 12 à 128 caractères.', csrf_token, 400)
    if not secrets.compare_digest(password, password_confirm):
        return _signup_response(request, 'Les deux mots de passe ne correspondent pas.', csrf_token, 400)

    user = User(email=normalized_email, password_hash=hash_password(password), name=display_name,
                ftp_watts=None, weight_kg=None, credit_tokens=0, model_choice='demo')
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        return _signup_response(request, 'Cette adresse email possède déjà un compte.', csrf_token, 409)

    _signup_attempts.pop(address, None)
    response = RedirectResponse('/app', status_code=303)
    response.set_cookie(COOKIE, sign_session(user.id), max_age=SESSION_SECONDS,
                        httponly=True, secure=True, samesite='lax', path='/')
    response.delete_cookie('coach_signup_csrf', path='/signup')
    return response


@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, 'login.html', {'error': None, 'allow_signup': ALLOW_SIGNUP})


# Lightweight per-process rate limit; nginx should add IP rate limiting for public exposure.
_attempts: dict[str, list[float]] = {}


@app.post('/login')
def login(request: Request, email: Annotated[str, Form()], password: Annotated[str, Form()], db: Session = Depends(get_db)):
    address = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    recent = [t for t in _attempts.get(address, []) if now - t < 60]
    if len(recent) >= 5:
        return templates.TemplateResponse(request, 'login.html', {'error': 'Trop de tentatives. Réessayez dans une minute.', 'allow_signup': ALLOW_SIGNUP}, status_code=429)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        _attempts[address] = recent + [now]
        return templates.TemplateResponse(request, 'login.html', {'error': 'Identifiants invalides.', 'allow_signup': ALLOW_SIGNUP}, status_code=401)
    _attempts.pop(address, None)
    response = RedirectResponse('/app', status_code=303)
    response.set_cookie(COOKIE, sign_session(user.id), max_age=SESSION_SECONDS,
                        httponly=True, secure=True, samesite='lax', path='/')
    return response


@app.post('/logout')
def logout():
    response = RedirectResponse('/login', status_code=303)
    response.delete_cookie(COOKIE, path='/')
    return response


@app.get('/app', response_class=HTMLResponse)
def coach_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    connection = db.scalar(select(StravaConnection).where(StravaConnection.user_id == user.id))
    return templates.TemplateResponse(request, 'coach.html', {'user': user, 'strava_connection': connection})


@app.get('/api/me')
def me(user: User = Depends(current_user)):
    return {'name': user.name, 'email': user.email, 'ftp_watts': user.ftp_watts,
            'weight_kg': float(user.weight_kg) if user.weight_kg is not None else None,
            'credit_tokens': user.credit_tokens, 'model_choice': user.model_choice,
            'demo': True}


@app.post('/api/profile')
async def update_profile(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Save athlete constants; true FTP/HRmax are preferred over estimates."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Invalid JSON body') from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail='Invalid JSON body')
    validators = {
        'weight_kg': (0.1, 300.0, float),
        'ftp_watts': (1, 2000, int),
        'max_heartrate': (30, 250, int),
    }
    for key, (low, high, cast) in validators.items():
        if key not in body:
            continue
        value = body[key]
        if value is None or value == '':
            setattr(user, key, None)
            continue
        try:
            parsed = cast(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise HTTPException(status_code=422, detail=f'{key} must be numeric') from exc
        if not low <= parsed <= high:
            raise HTTPException(status_code=422, detail=f'{key} is outside the accepted range')
        setattr(user, key, parsed)
    cache = db.get(LevelSnapshotCache, user.id)
    if cache is not None:
        db.delete(cache)
    db.commit()
    return {'status': 'saved', 'weight_kg': float(user.weight_kg) if user.weight_kg is not None else None,
            'ftp_watts': user.ftp_watts, 'max_heartrate': user.max_heartrate}


@app.get('/api/timeline')
def timeline(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rides = db.scalars(select(Activity).where(Activity.user_id == user.id)).all()
    docs = db.scalars(select(Artifact).where(Artifact.user_id == user.id)).all()
    items = [dict(id=a.id, type='activity', date=a.occurred_at.isoformat(), title=a.title,
                  subtype=a.sport, duration_minutes=a.duration_minutes,
                  distance_km=float(a.distance_km) if a.distance_km is not None else None) for a in rides]
    items += [dict(id=a.id, type='artifact', date=a.created_at.isoformat(), title=a.title,
                   subtype=a.category, duration_minutes=None, distance_km=None) for a in docs]
    items.sort(key=lambda x: x['date'], reverse=True)
    return items


@app.get('/api/timeline/{kind}/{item_id}')
def timeline_detail(kind: str, item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if kind == 'activity':
        item = db.get(Activity, item_id)
        if item is not None and item.user_id == user.id:
            return dict(type='activity', title=item.title, date=item.occurred_at.isoformat(),
                        duration_minutes=item.duration_minutes,
                        distance_km=float(item.distance_km) if item.distance_km is not None else None,
                        avg_watts=item.avg_watts, notes=item.notes)
    elif kind == 'artifact':
        item = db.get(Artifact, item_id)
        if item is not None and item.user_id == user.id:
            return dict(type='artifact', title=item.title, date=item.created_at.isoformat(),
                        markdown=item.markdown, related_activity_id=item.related_activity_id)
    raise HTTPException(status_code=404, detail='Not found')


def _compact_response(summary: dict) -> Response:
    payload = json.dumps(summary, ensure_ascii=False, separators=(',', ':'))
    return Response(content=payload, media_type='application/json',
                    headers={'X-Compact-Characters': str(len(payload))})


def _aware_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _parse_strava_datetime(value) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _as_number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@app.post('/api/activities/refresh')
def refresh_strava_activities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Import the latest 20 rides on first sync, then all activities newer than the cursor."""
    if user.weight_kg is None or float(user.weight_kg) <= 0:
        raise HTTPException(status_code=409, detail='Ajoutez un poids réel au profil avant de calculer les rapports compacts.')
    try:
        from services.strava_api import StravaAPIError, get_strava_client
        from services.strava_ingestion import sync_activities
        client = get_strava_client(db, user.id)
        return sync_activities(db, user.id, client)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StravaAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception('Unexpected Strava sync failure for Coach user id=%s', user.id)
        raise HTTPException(status_code=500, detail='Synchronisation Strava impossible ; consulter les journaux serveur.') from exc


@app.get('/api/activities/{activity_id}/compact')
def get_activity_compact(
    activity_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    segment: str | None = None,
):
    """Return cached compact JSON or build it from one high-resolution Strava fetch.

    `segment=longest` crops only the session summary; best_json stays full-ride.
    """
    activity = db.scalar(select(Activity).where(Activity.id == activity_id, Activity.user_id == user.id))
    if activity is None:
        raise HTTPException(status_code=404, detail='Activity not found')
    if segment is not None and segment != 'longest':
        try:
            start, end = (float(part) for part in segment.split('-', 1))
            if start < 0 or end <= start:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="segment must be 'longest' or START-END seconds")
    if segment is None and activity.compact_json is not None:
        return _compact_response(activity.compact_json)
    if user.weight_kg is None or float(user.weight_kg) <= 0:
        raise HTTPException(status_code=409, detail='Athlete weight is required for compact W/kg analysis')
    if activity.source_id is None:
        raise HTTPException(status_code=409, detail='Activity has no Strava source ID')
    try:
        from services.compact_ingestion import process_activity_streams
        from services.strava_api import get_strava_client
        client = get_strava_client(db, user.id)
        summary, _report = process_activity_streams(activity, user, client, segment=segment)
        if summary is None:
            raise HTTPException(status_code=422, detail='Compact summary unavailable for this activity')
        cache = db.get(LevelSnapshotCache, user.id)
        if cache is not None:
            db.delete(cache)
        db.commit()
        return _compact_response(summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.warning('Compact summary failed for activity=%s (%s)', activity.source_id, type(exc).__name__)
        raise HTTPException(status_code=502, detail='Unable to fetch/compact this Strava activity') from exc


@app.get('/api/level')
def get_level_snapshot(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cached 180-day source window; current 90 days vs prior 90 days, no Strava calls."""
    from services.strava_compact import level_snapshot
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=180)
    rows = db.execute(
        select(Activity.id, Activity.occurred_at, Activity.best_json)
        .where(Activity.user_id == user.id, Activity.occurred_at >= cutoff, Activity.best_json.is_not(None))
        .order_by(Activity.id)
    ).all()
    fingerprint = hashlib.sha256(json.dumps(
        [(row.id, _aware_datetime(row.occurred_at).isoformat(), row.best_json)
         for row in rows], sort_keys=True, separators=(',', ':'), default=str
    ).encode('utf-8')).hexdigest()
    cache = db.get(LevelSnapshotCache, user.id)
    if cache is not None:
        computed = _aware_datetime(cache.computed_at)
        if cache.source_signature == fingerprint and now - computed < timedelta(hours=6):
            return cache.snapshot_json
    best_rows = [(_aware_datetime(row.occurred_at).date(), row.best_json) for row in rows]
    weight = float(user.weight_kg) if user.weight_kg is not None else None
    snapshot = level_snapshot(best_rows, weight, today=now.date(), window_days=90)
    if cache is None:
        cache = LevelSnapshotCache(user_id=user.id, snapshot_json=snapshot,
                                   source_signature=fingerprint, computed_at=now)
        db.add(cache)
    else:
        cache.snapshot_json = snapshot
        cache.source_signature = fingerprint
        cache.computed_at = now
    db.commit()
    return snapshot
