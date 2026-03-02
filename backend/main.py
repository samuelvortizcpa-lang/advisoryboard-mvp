from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.clients import router as clients_router

# Create FastAPI app
app = FastAPI(
    title="AdvisoryBoard API",
    description="Client context management for CPA firms",
    version="1.0.0"
)

# Configure CORS - CRITICAL: Must be before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Root endpoint
@app.get("/")
async def root():
    return {"status": "AdvisoryBoard API is running"}


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy"}


# Include API routers
app.include_router(
    clients_router,
    prefix="/api",
    tags=["clients"]
)
