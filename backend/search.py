"""FastAPI router for search and event retrieval."""

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth import AuthError, AuthService
from backend.dependencies import authenticate
from backend.travel import Event


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    trip_id: str | None = Field(default=None, max_length=100)
    date_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    city: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("查詢字串不得為空或全為空白。")
        return trimmed

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                datetime.date.fromisoformat(v)
            except ValueError as exc:
                raise ValueError("日期格式無效。") from exc
        return v

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("起始日期不得晚於結束日期。")
        return self


class RelationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_id: str
    direction: str
    anchor_date: str
    target_date: str


class SearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Event
    score: float
    reasons: list[str]
    relation: RelationContext | None = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[SearchResultItem]
    clarification: str | None = None
    vector_status: str


class EventDetailResponse(Event):
    model_config = ConfigDict(extra="forbid")
    trip_name: str | None = None


def create_search_router(auth: AuthService, service: Any, prefix: str = "/api/v1") -> APIRouter:
    router = APIRouter(prefix=prefix)

    def _auth(request: Request, write: bool = False) -> str:
        try:
            return authenticate(auth, request, write=write)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)

    @router.post("/search", response_model=SearchResponse)
    def search(body: SearchInput, request: Request):
        owner_id = _auth(request, write=True)
        filters = {
            "trip_id": body.trip_id,
            "date_from": body.date_from,
            "date_to": body.date_to,
            "city": body.city,
            "category": body.category,
        }
        res = service.search(
            owner_id=owner_id,
            query=body.query,
            filters=filters,
            limit=body.limit,
        )
        return res

    @router.get("/search/status")
    def search_status(request: Request):
        owner_id = _auth(request, write=False)
        return service.index_status(owner_id)

    @router.get("/events/{id}", response_model=EventDetailResponse)
    def get_event(id: str, request: Request):
        owner_id = _auth(request, write=False)
        event_dict = service.get_event(owner_id, id)
        if not event_dict:
            raise HTTPException(status_code=404, detail="找不到指定的事件。")
        return event_dict

    return router
