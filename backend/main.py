import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()
logging.basicConfig(level=logging.INFO)

from api.auth import router as auth_router  # noqa: E402
from api.routes import router  # noqa: E402
from api.user import router as user_router  # noqa: E402

app = FastAPI(title="Stock Insight by NAD Technologies", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(router)
app.include_router(auth_router)
app.include_router(user_router)

# Hosted mode: when the built UI is copied to backend/static (see root Dockerfile), serve it from the same origin.
_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")
