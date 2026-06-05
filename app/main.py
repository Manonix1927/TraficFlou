from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from app.database import Base, engine
from app.routers import auth, projects

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TrafficFlow")

app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/")
def root():
    return RedirectResponse("/dashboard")
