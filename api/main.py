from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from db.database import init_db
from api.routes import auth, athlete, activities, sessions, competitions, comments, llm, calendar
import uvicorn

app = FastAPI(title="Strava Coach Dashboard")

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.on_event("startup")
def on_startup():
    init_db()

# Inclusion des routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(athlete.router, prefix="/api/athlete", tags=["athlete"])
app.include_router(activities.router, prefix="/api/activities", tags=["activities"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(competitions.router, prefix="/api/competitions", tags=["competitions"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])

# Route racine sans Jinja2
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("frontend/templates/index.html", "r") as f:
        html_content = f.read()
    return html_content

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=2024, reload=True)
