"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import ocp, optimize, simulate, sweep, tracks, transient

app = FastAPI(
    title="Lap Time Simulator API",
    description="QSS lap time simulation with track and vehicle management.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tracks.router, prefix="/tracks", tags=["tracks"])
app.include_router(simulate.router, prefix="/simulate", tags=["simulate"])
app.include_router(optimize.router, prefix="/optimize", tags=["optimize"])
app.include_router(ocp.router, prefix="/ocp", tags=["ocp"])
app.include_router(transient.router, prefix="/transient", tags=["transient"])
app.include_router(sweep.router, prefix="/sweep", tags=["sweep"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
