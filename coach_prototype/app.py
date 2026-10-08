"""Isolated cycling-coach prototype. No Strava or inference traffic in demo mode."""
import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, create_engine, select
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
    notes: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(Integer, unique=True)  # future external activity id


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
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OAuthState(Base):
    """Single-use OAuth CSRF state bound to a logged-in local user."""
    __tablename__ = 'coach_oauth_states'
    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('coach_users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


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
