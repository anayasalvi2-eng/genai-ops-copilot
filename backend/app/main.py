"""
GenAI Ops Copilot Platform — FastAPI Application Entry Point
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.routes import router

load_dotenv()

app = FastAPI(
    title="GenAI Ops Copilot Platform",
    description="Enterprise-grade multi-agent AI platform for DevOps intelligence",
    version="1.0.0",
)

# Allow requests from the React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "GenAI Ops Copilot"}
