from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
from app.api.routes import router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

app = FastAPI(
    title="Text-to-SQL API",
    description="Natural language to SQL with guardrails and hallucination detection",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/v1")


@app.get("/")
async def root():
    return {
        "service": "Text-to-SQL API",
        "version": "1.0.0",
        "docs": "/docs",
    }
