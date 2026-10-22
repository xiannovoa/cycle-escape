"""API FastAPI de Cycle Escape.

Expone el motor de routing con la forma exacta del contrato v0.1:

- ``GET /api/health``: diagnóstico del grafo y de las capas de tráfico.
- ``POST /api/escape-routes``: corredores de escape para un origen, sin destino.

El grafo se carga al arrancar desde la caché local, se enriquece con la capa
de tráfico medida (``data/raw/imd_santiago.geojson``) y solo después se calcula
el Road Stress. Si la capa no existe o no valida, el backend sigue funcionando
con estimaciones OSM. Si no hay grafo cacheado, arranca en estado ``degraded``
y responde 503 en lugar de intentar una descarga larga que rompería la demo.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import networkx as nx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.graph_loader import cache_path, get_graph
from app.escape_point import EscapeRouteResult, rank_escape_routes
from app.models import (
    SCHEMA_VERSION,
    ErrorDetail,
    ErrorResponse,
    EscapePoint,
    EscapeRoute,
    EscapeRoutesRequest,
    EscapeRoutesResponse,
    HealthResponse,
    LineString,
    Segment,
    TrafficSummary,
)
from app.routing import (
    NoCandidatesError,
    OriginOutsideCoverageError,
    PathEdge,
    route_candidates,
)
from app.scoring import score_graph_edges
from app.traffic_enrichment import enrich_graph_with_traffic

logger = logging.getLogger(__name__)

DIRECTION_LABELS: dict[str, str] = {
    "N": "Norte",
    "NE": "Noreste",
    "E": "Este",
    "SE": "Sureste",
    "S": "Sur",
    "SW": "Suroeste",
    "W": "Oeste",
    "NW": "Noroeste",
}

TRAFFIC_SOURCES = frozenset({"xunta", "mitma", "osm_estimate"})
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})

#: Capas de tráfico activas. Se ampliará cuando Eva integre Xunta y MITMA.
ACTIVE_TRAFFIC_LAYERS: tuple[str, ...] = ("osm_estimate",)

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
)


class ApiError(Exception):
    """Error de dominio con el formato estable del contrato."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


# --- Normalización de atributos para el contrato --------------------------


def _first_text(value: Any) -> str | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_float(value: Any) -> float | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_int(value: Any) -> int | None:
    number = _first_float(value)
    return int(round(number)) if number is not None else None


def _segment_from_edge(edge: PathEdge) -> Segment:
    attrs = edge.attrs
    source = _first_text(attrs.get("traffic_source")) or "osm_estimate"
    if source not in TRAFFIC_SOURCES:
        source = "osm_estimate"

    confidence = _first_text(attrs.get("traffic_confidence")) or "low"
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "low"

    imd = _first_float(attrs.get("imd"))
    year = _first_int(attrs.get("traffic_year"))
    heavy_pct = _first_float(attrs.get("heavy_pct"))

    if imd is not None and imd < 0:
        imd = None
    if year is not None and not 1900 <= year <= 2100:
        year = None

    if source == "osm_estimate":
        # Regla del contrato: una estimación no puede llevar aforo medido.
        imd = None
        year = None
        heavy_pct = None
        if confidence not in {"low", "medium"}:
            confidence = "low"
    elif imd is None:
        confidence = "low"

    if heavy_pct is not None and not 0 <= heavy_pct <= 100:
        heavy_pct = None

    return Segment(
        geometry=LineString(
            coordinates=[(float(lon), float(lat)) for lon, lat in edge.coordinates]
        ),
        road_name=_first_text(attrs.get("name"))
        or _first_text(attrs.get("ref")),
        highway=_first_text(attrs.get("highway")),
        surface=_first_text(attrs.get("surface")),
        road_stress=edge.road_stress,
        imd=imd,
        heavy_pct=heavy_pct,
        traffic_source=source,
        traffic_year=year,
        traffic_confidence=confidence,
    )


def _traffic_summary(
    segments: list[Segment], edges: tuple[PathEdge, ...]
) -> TrafficSummary:
    sources: list[str] = []
    years: set[int] = set()
    measured_length_m = 0.0
    total_length_m = 0.0
    measured_confidences: list[str] = []

    for segment, edge in zip(segments, edges):
        total_length_m += max(0.0, edge.length_m)
        if segment.traffic_source not in sources:
            sources.append(segment.traffic_source)

        if segment.traffic_source != "osm_estimate":
            measured_length_m += max(0.0, edge.length_m)
            measured_confidences.append(segment.traffic_confidence)
            if segment.traffic_year is not None:
                years.add(segment.traffic_year)

    measured_share = (
        measured_length_m / total_length_m if total_length_m > 0 else 0.0
    )

    if measured_share == 0:
        # Contrato: low = sin aforo; medium = cobertura parcial o aforo antiguo.
        confidence = "low"
    elif (
        measured_share >= 0.75
        and measured_confidences
        and all(value == "high" for value in measured_confidences)
    ):
        confidence = "high"
    else:
        confidence = "medium"

    return TrafficSummary(
        sources=sources or ["osm_estimate"],
        years=sorted(years),
        measured_share=round(measured_share, 3),
        confidence=confidence,
    )


def _route_warnings(result: EscapeRouteResult, summary: TrafficSummary) -> list[str]:
    warnings = list(result.warnings)

    if summary.measured_share == 0:
        warnings.append("Toda la ruta usa estimación OSM: no hay aforo medido.")
    elif summary.measured_share < 1:
        warnings.append("Incluye tramos sin aforo estimados con OSM.")

    if any(year < 2023 for year in summary.years):
        warnings.append("Parte de los aforos son anteriores a 2023.")

    return list(dict.fromkeys(warnings))


def _label(result: EscapeRouteResult) -> str:
    direction = DIRECTION_LABELS[result.direction]
    if result.escape_point.name:
        return f"{direction} vía {result.escape_point.name}"
    return f"Salida {direction.lower()}"


def _route_to_model(result: EscapeRouteResult) -> EscapeRoute:
    segments = [_segment_from_edge(edge) for edge in result.edges]
    summary = _traffic_summary(segments, result.edges)

    return EscapeRoute(
        id=result.id,
        label=_label(result),
        direction=result.direction,
        is_recommended=result.is_recommended,
        escape_time_min=result.escape_time_min,
        distance_to_escape_km=result.distance_to_escape_km,
        quiet_score=result.quiet_score,
        avg_road_stress=result.avg_road_stress,
        escape_point=EscapePoint(
            lat=result.escape_point.lat,
            lon=result.escape_point.lon,
            name=result.escape_point.name,
        ),
        geometry=LineString(
            coordinates=[(float(lon), float(lat)) for lon, lat in result.geometry]
        ),
        segments=segments,
        traffic_summary=summary,
        warnings=_route_warnings(result, summary),
    )


def _global_warnings(routes: list[EscapeRoute]) -> list[str]:
    warnings: list[str] = []
    if routes and all(route.traffic_summary.measured_share == 0 for route in routes):
        warnings.append(
            "Los datos de tráfico son parciales: no hay aforos medidos "
            "cargados y todas las estimaciones usan OSM."
        )
    return warnings


def _request_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"req_{stamp}_{uuid.uuid4().hex[:6]}"


# --- Carga del grafo -------------------------------------------------------


def _try_load_graph(app: FastAPI) -> None:
    path = cache_path()
    if not path.exists():
        app.state.graph_error = f"no hay caché de grafo en {path}"
        logger.warning(
            "Grafo no cacheado (%s). Ejecuta: python -m app.graph_loader", path
        )
        return

    try:
        started = time.perf_counter()
        graph = get_graph()

        layers = list(ACTIVE_TRAFFIC_LAYERS)
        try:
            report = enrich_graph_with_traffic(graph)
            if report.sources:
                layers = [
                    source
                    for source in ("xunta", "mitma")
                    if source in report.sources
                ] + ["osm_estimate"]
            app.state.traffic_report = report
            logger.info(
                "Tráfico asociado: %d/%d tramos, %d aristas, %.1f km",
                report.matched_segments,
                report.total_segments,
                report.matched_edges,
                report.matched_length_km,
            )
        except Exception as exc:  # capa ausente, esquema inválido, geopandas...
            app.state.traffic_error = str(exc)
            logger.warning("Sin enriquecimiento de tráfico: %s", exc)

        # Puntuar siempre después de enriquecer: si no, el Road Stress se
        # quedaría calculado solo con OSM.
        score_graph_edges(graph)

        app.state.graph = graph
        app.state.traffic_layers = layers
        logger.info(
            "Grafo cargado en %.1f s: %d nodos, %d aristas, capas=%s",
            time.perf_counter() - started,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            layers,
        )
    except Exception as exc:  # caché corrupta, dependencia rota, etc.
        app.state.graph_error = str(exc)
        logger.exception("No se pudo cargar el grafo OSM")


# --- Aplicación ------------------------------------------------------------


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code=exc.code,  # type: ignore[arg-type]
                message=exc.message,
                details=exc.details,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(payload),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        touches_origin = any(
            "origin" in error.get("loc", ()) for error in errors
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code="INVALID_ORIGIN" if touches_origin else "INVALID_PARAMETER",
                message="La petición no cumple el contrato.",
                details={"errors": jsonable_encoder(errors)},
            )
        )
        return JSONResponse(
            status_code=400, content=jsonable_encoder(payload)
        )

    @app.exception_handler(OriginOutsideCoverageError)
    async def handle_outside_coverage(
        request: Request, exc: OriginOutsideCoverageError
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="OUTSIDE_COVERAGE",
                message="El origen está fuera de la zona con datos cargados.",
                details={},
            )
        )
        return JSONResponse(
            status_code=404, content=jsonable_encoder(payload)
        )

    @app.exception_handler(NoCandidatesError)
    async def handle_no_candidates(
        request: Request, exc: NoCandidatesError
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="NO_ROUTES_FOUND",
                message="No se han encontrado corredores de escape para este origen.",
                details={},
            )
        )
        return JSONResponse(
            status_code=404, content=jsonable_encoder(payload)
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Error no controlado en %s", request.url.path)
        payload = ErrorResponse(
            error=ErrorDetail(
                code="ROUTING_ERROR",
                message="No se ha podido calcular la ruta.",
                details={},
            )
        )
        return JSONResponse(
            status_code=500, content=jsonable_encoder(payload)
        )


def create_app(
    *,
    graph: nx.MultiDiGraph | None = None,
    load_graph: bool = True,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Crea la app. En tests se puede inyectar un grafo y evitar la carga."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if load_graph and app.state.graph is None:
            _try_load_graph(app)
        yield

    app = FastAPI(
        title="Cycle Escape API",
        version=SCHEMA_VERSION,
        lifespan=lifespan,
    )
    app.state.graph = graph
    app.state.graph_error = None
    app.state.traffic_layers = list(ACTIVE_TRAFFIC_LAYERS)
    app.state.traffic_report = None
    app.state.traffic_error = None

    origins = cors_origins
    if origins is None:
        raw = os.getenv("CYCLE_ESCAPE_CORS_ORIGINS")
        origins = (
            [origin.strip() for origin in raw.split(",") if origin.strip()]
            if raw
            else list(DEFAULT_CORS_ORIGINS)
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_error_handlers(app)

    @app.get("/api/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        loaded = request.app.state.graph is not None
        return HealthResponse(
            status="ok" if loaded else "degraded",
            osm_graph_loaded=loaded,
            traffic_layers=list(request.app.state.traffic_layers)
            or list(ACTIVE_TRAFFIC_LAYERS),
            schema_version=SCHEMA_VERSION,
        )

    @app.post("/api/escape-routes", response_model=EscapeRoutesResponse)
    def escape_routes(
        request: Request, payload: EscapeRoutesRequest
    ) -> EscapeRoutesResponse:
        graph = request.app.state.graph
        if graph is None:
            raise ApiError(
                503,
                "DATA_NOT_READY",
                "El grafo OSM no está cargado. Ejecuta el cargador del backend.",
            )

        started = time.perf_counter()

        # Nota: surface_preference se acepta en el contrato, pero el Road Stress
        # ya penaliza las superficies no asfaltadas. No se ignora en silencio:
        # queda documentado para una iteración posterior.
        candidates = route_candidates(
            graph,
            payload.origin.lat,
            payload.origin.lon,
            avg_speed_kmh=payload.avg_speed_kmh,
            traffic_aversion=payload.traffic_aversion,
        )
        ranked = rank_escape_routes(
            candidates,
            route_preference=payload.route_preference,
            max_routes=payload.max_candidates,
            graph=graph,
        )

        routes = [_route_to_model(result) for result in ranked]
        if not routes:
            raise NoCandidatesError("no hay rutas que devolver")

        recommended_route_id = next(
            (route.id for route in routes if route.is_recommended),
            routes[0].id,
        )

        response = EscapeRoutesResponse(
            schema_version=SCHEMA_VERSION,
            request_id=_request_id(),
            generated_at=datetime.now(timezone.utc),
            origin=payload.origin,
            recommended_route_id=recommended_route_id,
            routes=routes,
            warnings=_global_warnings(routes),
        )

        logger.info(
            "escape-routes origin=%.5f,%.5f aversion=%.2f preference=%s "
            "routes=%d en %.1f s",
            payload.origin.lat,
            payload.origin.lon,
            payload.traffic_aversion,
            payload.route_preference,
            len(routes),
            time.perf_counter() - started,
        )
        return response

    return app


app = create_app()
