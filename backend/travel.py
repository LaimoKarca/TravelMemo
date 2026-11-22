import datetime
import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth import AuthError, AuthService
from backend.locations import MAX_MAP_URL_LENGTH, parse_location
from backend.timezones import normalize_timezone, resolve_timezone
from backend.travel_store import (
    TravelConflictError,
    TravelNotFoundError,
    TravelValidationError,
)


class TripCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: str = Field(default="Asia/Taipei")
    description: str = Field(default="", max_length=10000)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            return normalize_timezone(v)
        except ValueError:
            raise ValueError(f"無效的時區: {v}")

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            s = datetime.date.fromisoformat(self.start_date)
            e = datetime.date.fromisoformat(self.end_date)
        except ValueError:
            raise ValueError("日期格式無效")
        if s > e:
            raise ValueError("開始日期不得晚於結束日期")
        return self


class TripUpdate(TripCreate):
    version: int


class Trip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    start_date: str
    end_date: str
    timezone: str
    description: str
    version: int


class TripListItem(Trip):
    cover_photo_id: str | None = None


class TripsList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TripListItem]


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    city: str
    address: str
    map_url: str | None = None


class PlacesList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Place]


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_id: str | None = None
    place_name: str = Field(min_length=1, max_length=200)
    city: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=MAX_MAP_URL_LENGTH)
    map_url: str | None = Field(default=None, max_length=MAX_MAP_URL_LENGTH)
    category: str = Field(min_length=1, max_length=200)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    notes: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def validate_location(self):
        location = parse_location(self.address, self.map_url)
        self.address = location["address"]
        if location["map_url"] is not None or "map_url" in self.model_fields_set:
            self.map_url = location["map_url"]
        return self

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError("日期格式無效")
        return v


class EventUpdate(EventCreate):
    version: int
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        return normalize_timezone(value) if value is not None else None


class StandaloneEventCreate(EventCreate):
    category: str = Field(default="未分類", min_length=1, max_length=200)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: str = "Asia/Taipei"

    @field_validator("date")
    @classmethod
    def validate_date(cls, value):
        return EventCreate.validate_date(value) if value is not None else None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        return normalize_timezone(value)

    @model_validator(mode="after")
    def default_date(self):
        if self.date is None:
            self.date = datetime.datetime.now(resolve_timezone(self.timezone)).date().isoformat()
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    trip_id: str | None
    place_id: str
    place_name: str
    city: str
    address: str
    map_url: str | None = None
    category: str
    date: str
    time: str | None
    notes: str
    position: int | None
    version: int
    timezone: str = "Asia/Taipei"
    record_scope: str = "trip"


class StandaloneEventsList(BaseModel):
    items: list[Event]
    next_offset: int | None


class AttachEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trip_id: str
    version: int = Field(ge=1)
    trip_version: int = Field(ge=1)
    before_event_id: str | None = None


class NextEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_id: str
    to_id: str


class TripDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trip: Trip
    events: list[Event]
    next_edges: list[NextEdge]


class EventOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    event_ids: list[str]


def create_travel_router(auth: AuthService, repository: Any, prefix: str = "/api/v1", photo_service: Any = None) -> APIRouter:
    router = APIRouter(prefix=prefix)
    if photo_service is not None and hasattr(repository, "photo_store"):
        repository.photo_store = photo_service.store

    def authenticate(request: Request, require_csrf: bool = False) -> str:
        token = request.cookies.get("travelmemo_session")
        if not token:
            raise HTTPException(status_code=401, detail="請先登入。")
        try:
            session_record = auth.session(token)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)

        if require_csrf:
            csrf = request.headers.get("X-CSRF-Token")
            if not csrf or not hmac.compare_digest(session_record["csrf_token"], csrf):
                raise HTTPException(status_code=403, detail="登入驗證已變更，請重新整理頁面。")

        return session_record["user"]["id"]

    @router.get("/trips", response_model=TripsList)
    def list_trips(request: Request):
        owner_id = authenticate(request, require_csrf=False)
        items = repository.get_trips(owner_id, include_cover=True)
        return {"items": items}

    @router.post("/trips", response_model=Trip, status_code=201)
    def create_trip(body: TripCreate, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            trip = repository.create_trip(owner_id, body.model_dump())
            return trip
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    @router.get("/trips/{id}", response_model=TripDetail)
    def get_trip(id: str, request: Request):
        owner_id = authenticate(request, require_csrf=False)
        detail = repository.get_trip_detail(owner_id, id)
        if not detail:
            raise HTTPException(status_code=404, detail="找不到指定的旅程。")
        return detail

    @router.put("/trips/{id}", response_model=Trip)
    def update_trip(id: str, body: TripUpdate, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            trip = repository.update_trip(owner_id, id, body.model_dump())
            return trip
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.message)
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    @router.delete("/trips/{id}", status_code=204)
    def delete_trip(id: str, request: Request, version: int = Query(...)):
        owner_id = authenticate(request, require_csrf=True)
        try:
            detail = repository.get_trip_detail(owner_id, id) if photo_service is not None else None
            repository.delete_trip(owner_id, id, version)
            if photo_service is not None:
                for event in (detail or {}).get("events", []):
                    photo_service.detach_target(owner_id, "event", event["id"])
                photo_service.detach_target(owner_id, "trip", id)
            return Response(status_code=204)
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.message)

    @router.get("/places", response_model=PlacesList)
    def list_places(request: Request):
        owner_id = authenticate(request, require_csrf=False)
        items = repository.get_places(owner_id)
        return {"items": items}

    @router.post("/trips/{id}/events", response_model=Event, status_code=201)
    def create_event(id: str, body: EventCreate, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            event = repository.create_event(owner_id, id, body.model_dump())
            return event
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    @router.get("/events", response_model=StandaloneEventsList)
    def list_standalone_events(request: Request, q: str = Query(default="", max_length=500),
                               city: str | None = None, category: str | None = None,
                               date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                               date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                               limit: int = Query(default=20, ge=1, le=100),
                               offset: int = Query(default=0, ge=0)):
        owner_id = authenticate(request)
        try:
            for value in (date_from, date_to):
                if value is not None:
                    datetime.date.fromisoformat(value)
            if date_from and date_to and date_from > date_to:
                raise ValueError("開始日期不得晚於結束日期。")
        except ValueError:
            raise HTTPException(status_code=422, detail="日期範圍無效。")
        return repository.list_standalone_events(owner_id, q=q, city=city, category=category,
                                                 date_from=date_from, date_to=date_to,
                                                 limit=limit, offset=offset)

    @router.post("/events", response_model=Event, status_code=201)
    def create_standalone_event(body: StandaloneEventCreate, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            return repository.create_standalone_event(owner_id, body.model_dump())
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    @router.post("/events/{id}/attach-trip", response_model=Event)
    def attach_event(id: str, body: AttachEventInput, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            return repository.attach_event_to_trip(owner_id, id, body.model_dump())
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.message)
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    @router.put("/events/{id}", response_model=Event)
    def update_event(id: str, body: EventUpdate, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            data = body.model_dump()
            if "map_url" not in body.model_fields_set:
                del data["map_url"]
            event = repository.update_event(owner_id, id, data)
            return event
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.message)
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    @router.delete("/events/{id}", status_code=204)
    def delete_event(id: str, request: Request, version: int = Query(...)):
        owner_id = authenticate(request, require_csrf=True)
        try:
            repository.delete_event(owner_id, id, version)
            if photo_service is not None:
                photo_service.detach_target(owner_id, "event", id)
            return Response(status_code=204)
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.message)

    @router.put("/trips/{id}/event-order", response_model=TripDetail)
    def reorder_events(id: str, body: EventOrderInput, request: Request):
        owner_id = authenticate(request, require_csrf=True)
        try:
            detail = repository.reorder_events(owner_id, id, body.version, body.event_ids)
            return detail
        except TravelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
        except TravelConflictError as exc:
            raise HTTPException(status_code=409, detail=exc.message)
        except TravelValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message)

    return router
