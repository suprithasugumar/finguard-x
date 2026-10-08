"""FinGuard-X FastAPI application entrypoint."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.endpoints import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finguard.main")

app = FastAPI(
    title="FinGuard-X API",
    description="Multimodal Financial Fraud Detection Platform (SEC EDGAR, NetworkX, MiniLM, TreeSHAP)",
    version="1.0.0",
)

# Enable CORS for frontend Vite development server and production builds
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "FinGuard-X API", "version": "1.0.0"}


# Mount frontend dist static files for full single-port experience
dist_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if dist_path.exists():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
