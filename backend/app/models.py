"""Modelos del contrato de API de Cycle Escape (v0.1).

Traducen `docs/api-contract.md` a tipos validables. Son la frontera entre el
motor de routing y el frontend: lo que no encaje aquí no debería salir por la API.

Convenciones (ver `AGENTS.md`):
- JSON en `snake_case`.
- Geometrías GeoJSON con coordenadas ``[lon, lat]``.
- ``road_stress`` y ``quiet_score`` en escala 0-100.
- ``None`` significa "sin dato"; nunca se usa 0 como sustituto.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

#: Versión del contrato que implementan estos modelos.
SCHEMA_VERSION = "0.1"

DEFAULT_AVG_SPEED_KMH = 22.0
DEFAULT_TRAFFIC_AVERSION = 0.5
DEFAULT_MAX_CANDIDATES = 5
MAX_CANDIDATES = 7

Direction = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
DIRECTIONS: tuple[Direction, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

TrafficSource = Literal["xunta", "mitma", "osm_estimate"]
TrafficConfidence = Literal["high", "medium", "low"]
SurfacePreference = Literal["asphalt", "mixed", "any"]
RoutePreference = Literal["direct", "balanced", "quiet"]
ErrorCode = Literal[
    "INVALID_ORIGIN",
    "INVALID_PARAMETER",
    "OUTSIDE_COVERAGE",
    "NO_ROUTES_FOUND",
    "ROUTING_ERROR",
    "DATA_NOT_READY",
]

#: Puntuación 0-100 (estrés alto = peor; QuietScore alto = mejor).
Score = Annotated[float, Field(ge=0, le=100)]


class LatLon(BaseModel):
    """Punto geográfico en grados WGS84."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LineString(BaseModel):
    """Geometría GeoJSON ``LineString`` con coordenadas ``[lon, lat]``."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]] = Field(min_length=2)

    @field_validator("coordinates")
    @classmethod
    def _check_coordinate_ranges(
        cls, coordinates: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        for lon, lat in coordinates:
            if not -180.0 <= lon <= 180.0:
                raise ValueError(f"longitud fuera de rango: {lon}")
            if not -90.0 <= lat <= 90.0:
                raise ValueError(f"latitud fuera de rango: {lat}")
        return coordinates


class EscapePoint(BaseModel):
    """Primer punto desde el que la red siguiente es sostenidamente tranquila."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    #: Nombre legible opcional (lugar o vía cercana); el frontend puede omitirlo.
    name: str | None = None


class Segment(BaseModel):
    """Tramo de ruta con su estrés y su procedencia de datos de tráfico."""

    geometry: LineString
    road_name: str | None = None
    highway: str | None = None
    surface: str | None = None
    road_stress: Score

    #: IMD en vehículos/día. ``None`` si no hay aforo; nunca 0 por defecto.
    imd: float | None = Field(default=None, ge=0)
    #: Porcentaje de vehículos pesados (0-100), no fracción.
    heavy_pct: float | None = Field(default=None, ge=0, le=100)
    traffic_source: TrafficSource
    traffic_year: int | None = Field(default=None, ge=1900, le=2100)
    traffic_confidence: TrafficConfidence

    @model_validator(mode="after")
    def _check_traffic_consistency(self) -> Segment:
        if self.traffic_source == "osm_estimate":
            if self.imd is not None or self.traffic_year is not None:
                raise ValueError(
                    "un tramo osm_estimate no puede llevar imd ni traffic_year"
                )
        elif self.imd is None and self.traffic_confidence != "low":
            raise ValueError(
                "un tramo medido sin imd debe declararse con confianza 'low'"
            )
        return self


class TrafficSummary(BaseModel):
    """Cobertura y confianza agregadas de los datos de tráfico de una ruta."""

    sources: list[TrafficSource] = Field(min_length=1)
    years: list[int] = Field(default_factory=list)
    #: Fracción 0-1 de la distancia recorrida con aforo medido.
    measured_share: float = Field(ge=0, le=1)
    confidence: TrafficConfidence

    @model_validator(mode="after")
    def _check_measured_share(self) -> TrafficSummary:
        has_measured = any(source != "osm_estimate" for source in self.sources)
        if self.measured_share > 0 and not has_measured:
            raise ValueError(
                "measured_share > 0 requiere alguna fuente medida (xunta o mitma)"
            )
        return self


class EscapeRoute(BaseModel):
    """Corredor de escape candidato, listo para pintar en el mapa."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    direction: Direction
    is_recommended: bool
    #: Tiempo desde el origen hasta el Escape Point.
    escape_time_min: float = Field(ge=0)
    #: Distancia recorrida desde el origen hasta el Escape Point.
    distance_to_escape_km: float = Field(ge=0)
    #: QuietScore de la red posterior al Escape Point.
    quiet_score: Score
    avg_road_stress: Score | None = None
    escape_point: EscapePoint
    geometry: LineString
    segments: list[Segment] = Field(default_factory=list)
    traffic_summary: TrafficSummary
    warnings: list[str] = Field(default_factory=list)


class EscapeRoutesRequest(BaseModel):
    """Petición de corredores de escape para un origen sin destino."""

    origin: LatLon
    avg_speed_kmh: float = Field(
        default=DEFAULT_AVG_SPEED_KMH, ge=10, le=35
    )
    #: 0 = tolera el tráfico, 1 = lo evita a toda costa.
    traffic_aversion: float = Field(
        default=DEFAULT_TRAFFIC_AVERSION, ge=0, le=1
    )
    surface_preference: SurfacePreference = "asphalt"
    route_preference: RoutePreference = "balanced"
    max_candidates: int = Field(
        default=DEFAULT_MAX_CANDIDATES, ge=1, le=MAX_CANDIDATES
    )


class EscapeRoutesResponse(BaseModel):
    """Respuesta completa: ruta recomendada y alternativas ordenadas."""

    schema_version: str = SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    generated_at: datetime
    origin: LatLon
    recommended_route_id: str = Field(min_length=1)
    routes: list[EscapeRoute] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_serializer("generated_at")
    def _serialize_generated_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    @model_validator(mode="after")
    def _check_recommended_route(self) -> EscapeRoutesResponse:
        route_ids = [route.id for route in self.routes]
        if len(set(route_ids)) != len(route_ids):
            raise ValueError("los id de las rutas deben ser únicos")

        if self.recommended_route_id not in route_ids:
            raise ValueError(
                "recommended_route_id no corresponde a ninguna ruta devuelta"
            )

        flagged = [route.id for route in self.routes if route.is_recommended]
        if flagged != [self.recommended_route_id]:
            raise ValueError(
                "is_recommended debe estar marcado exactamente en la ruta recomendada"
            )
        return self


class HealthResponse(BaseModel):
    """Estado del backend para diagnóstico del frontend."""

    status: Literal["ok", "degraded"]
    osm_graph_loaded: bool
    traffic_layers: list[str] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Formato estable de error para todos los endpoints."""

    error: ErrorDetail


__all__ = [
    "DEFAULT_AVG_SPEED_KMH",
    "DEFAULT_MAX_CANDIDATES",
    "DEFAULT_TRAFFIC_AVERSION",
    "DIRECTIONS",
    "MAX_CANDIDATES",
    "SCHEMA_VERSION",
    "Direction",
    "EscapePoint",
    "EscapeRoute",
    "EscapeRoutesRequest",
    "EscapeRoutesResponse",
    "ErrorCode",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "LatLon",
    "LineString",
    "RoutePreference",
    "Score",
    "Segment",
    "SurfacePreference",
    "TrafficConfidence",
    "TrafficSource",
    "TrafficSummary",
]
