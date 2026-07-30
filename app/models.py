from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl
    instructions: str = Field(
        default="Extract the useful information and remove navigation, ads, and repeated boilerplate.",
        max_length=2_000,
    )


class ScrapeResponse(BaseModel):
    url: str
    title: str
    method: Literal["http", "browser"]
    raw_text: str
    cleaned_text: str
    llm_used: bool
    author: str | None = None
    published_date: str | None = None
    description: str | None = None
    warning: str | None = None


class ApprovalRequest(BaseModel):
    url: HttpUrl
    title: str = Field(max_length=500)
    content: str = Field(min_length=1, max_length=200_000)


class ApprovalResponse(BaseModel):
    status: Literal["approved"]
    title: str
    content: str

