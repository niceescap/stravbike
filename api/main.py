from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from db.database import init_db
from api.routes import auth, athlete, activities, sessions, competitions, comments, llm, calendar
import uvicorn
from dotenv import load_dotenv
load_dotenv()
from api.dependencies import verify_service_key


app = FastAPI(title="Strava Coach Dashboard")

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.on_event("startup")
def on_startup():
    init_db()

# Inclusion des routers
# auth.router reste SANS clé de service : c'est le magic link humain, système à part
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# Ces routers sont protégés par la clé de service (utilisée par l'outil Open WebUI)
app.include_router(athlete.router, prefix="/api/athlete", tags=["athlete"], dependencies=[Depends(verify_service_key)])
app.include_router(activities.router, prefix="/api/activities", tags=["activities"], dependencies=[Depends(verify_service_key)])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(verify_service_key)])
app.include_router(competitions.router, prefix="/api/competitions", tags=["competitions"], dependencies=[Depends(verify_service_key)])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"], dependencies=[Depends(verify_service_key)])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"], dependencies=[Depends(verify_service_key)])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"], dependencies=[Depends(verify_service_key)])

# Route racine sans Jinja2
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("frontend/templates/index.html", "r") as f:
        html_content = f.read()
    return html_content

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=2024, reload=True)
