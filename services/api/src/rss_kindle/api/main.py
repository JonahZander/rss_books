from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from portfolio_api.config import get_settings


class HealthResponse(BaseModel):
    status: str


class ProfileResponse(BaseModel):
    name: str
    role: str
    summary: str
    location: str
    featured_focus: list[str]


settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse(status="ready")


@app.get("/api/v1/profile", response_model=ProfileResponse)
def profile() -> ProfileResponse:
    return ProfileResponse(
        name="Jonah Zander",
        role="Product-minded engineer",
        summary=(
            "Portfolio API starter for powering site metadata, structured case studies, "
            "and future contact or writing workflows."
        ),
        location="Los Angeles, CA",
        featured_focus=[
            "Product engineering",
            "AI-native tooling",
            "Design systems",
        ],
    )
