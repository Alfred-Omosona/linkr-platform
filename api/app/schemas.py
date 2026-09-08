"""Request/response contracts. These are the API's public surface."""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class LinkCreate(BaseModel):
    url: HttpUrl = Field(..., description="Absolute http(s) URL to shorten.")
    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Optional vanity code. Generated if omitted.",
    )


class LinkOut(BaseModel):
    code: str
    short_url: str
    target_url: str
    hits: int
    created_at: datetime
    last_hit_at: datetime | None = None


class StatsOut(BaseModel):
    total_links: int
    total_hits: int


class HealthOut(BaseModel):
    status: str
    env: str
    version: str
    git_sha: str
