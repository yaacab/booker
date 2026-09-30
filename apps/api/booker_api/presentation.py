"""Public artist presentation. No fee, trust or availability mutations."""
import ipaddress
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from booker_api.commerce.entitlements import get_entitlements
from booker_api.models import Artist, ArtistPresentation


def public_media_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("Используйте публичную HTTPS-ссылку без пароля")
    if host == "localhost" or "." not in host or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Нужна публичная ссылка")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Нужна публичная ссылка")
    return value


MediaUrl = Annotated[str, Field(max_length=2048), AfterValidator(public_media_url)]
ShortText = Annotated[str, Field(min_length=1, max_length=128)]


class MediaLink(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: MediaUrl
    label: str = Field(default="", max_length=128)
    kind: Literal["video", "audio"] = "video"


class TechnicalRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage_area_m2: float | None = Field(default=None, ge=0, le=10000)
    power_kw: float | None = Field(default=None, ge=0, le=10000)
    basic_sound: bool | None = None
    microphones: int | None = Field(default=None, strict=True, ge=0, le=100)
    setup_minutes: int | None = Field(default=None, strict=True, ge=0, le=1440)
    teardown_minutes: int | None = Field(default=None, strict=True, ge=0, le=1440)
    required_equipment: list[ShortText] | None = Field(default=None, max_length=30)
    supplied_equipment: list[ShortText] | None = Field(default=None, max_length=30)


class PresentationData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    cover_url: MediaUrl = ""
    primary_video_url: MediaUrl = ""
    gallery: list[MediaUrl] = Field(default_factory=list, max_length=24)
    links: list[MediaLink] = Field(default_factory=list, max_length=12)
    format: str = Field(default="", max_length=300)
    lineup: str = Field(default="", max_length=500)
    program: str = Field(default="", max_length=4000)
    genres: list[ShortText] = Field(default_factory=list, max_length=20)
    duration_minutes: int | None = Field(default=None, strict=True, ge=1, le=1440)
    travel_cities: list[ShortText] = Field(default_factory=list, max_length=30)
    rider_text: str = Field(default="", max_length=4000)
    technical: TechnicalRequirements = Field(default_factory=TechnicalRequirements)
    layout: Literal["standard", "gallery_first"] = "standard"
    media_rights_confirmed: bool = False

    @model_validator(mode="after")
    def media_consent(self):
        if any(not u for u in self.gallery) or any(not link.url for link in self.links):
            raise ValueError("Для каждого материала нужна ссылка")
        if (self.cover_url or self.primary_video_url or self.gallery or self.links) and not self.media_rights_confirmed:
            raise ValueError("Подтвердите право публиковать выбранные материалы")
        return self


def presentation_data(db: Session, artist: Artist) -> tuple[int, dict]:
    row = db.get(ArtistPresentation, artist.id)
    if row:
        return row.version, json.loads(row.data_json)
    try:
        rider = json.loads(artist.rider_json or "{}")
    except (ValueError, TypeError):
        rider = {}
    if not isinstance(rider, dict):
        rider = {}
    # Legacy free-form data stays visible. No rights assertion or invented media.
    return 0, PresentationData(
        name=artist.name, city=artist.city, category=artist.category,
        format=str(rider.get("format") or "")[:300],
        lineup=str(rider.get("lineup") or "")[:500],
        rider_text=str(rider.get("tech") or "")[:4000],
    ).model_dump()


def presentation_limits(db: Session, artist: Artist) -> dict:
    features = get_entitlements(db, artist.organization_id)["features"]
    advanced = bool(features.get("portfolio.advanced"))
    return {"gallery": 24 if advanced else 6, "links": 12 if advanced else 3,
            "travel_cities": 30 if features.get("geography.advanced") else 3,
            "advanced_layout": advanced}
