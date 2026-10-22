"""Enriquecimiento del grafo OSM con la capa de tráfico medida de Eva.

Estrategia acordada en `docs/data-normalization.md`:

1. filtrar por ``ref`` compatible entre la carretera de la capa y la arista OSM;
2. exigir una distancia geométrica <= 30 m;
3. no asociar por proximidad sin ``ref`` (hay calles urbanas pegadas a la N-550);
4. si varias observaciones compiten por una arista, gana la más cercana, luego
   la de mayor confianza, luego la más reciente y, por seguridad, la de mayor IMD.

El módulo no descarga ni normaliza datos: consume ``load_traffic_segments()`` de
``app.data_loader`` (ámbito de Eva) y escribe en las aristas los campos del
contrato. Después hay que volver a puntuar el grafo con ``score_graph_edges``.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import geopandas as gpd
import networkx as nx
from shapely import wkt
from shapely.geometry import LineString

from app.data_loader import load_traffic_segments

logger = logging.getLogger(__name__)

#: Buffer máximo de asociación geométrica, en metros.
MATCH_BUFFER_M = 30.0

MEASURED_SOURCES = frozenset({"xunta", "mitma"})
CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}

REQUIRED_COLUMNS = (
    "road_ref",
    "imd",
    "heavy_pct",
    "traffic_source",
    "traffic_year",
    "traffic_confidence",
    "geometry",
)


class TrafficEnrichmentError(RuntimeError):
    """La capa de tráfico no tiene el esquema esperado o no se puede usar."""


@dataclass(frozen=True)
class TrafficMatch:
    """Observación de tráfico asociada a una arista OSM."""

    edge: tuple[int, int, int]
    distance_m: float
    imd: int
    heavy_pct: float | None
    source: str
    year: int | None
    confidence: str
    road_ref: str


@dataclass(frozen=True)
class EnrichmentReport:
    """Resumen del matching para logs y diagnóstico."""

    matched_edges: int
    total_edges: int
    matched_segments: int
    total_segments: int
    matched_length_km: float
    total_length_km: float
    sources: tuple[str, ...]
    missing_segments: tuple[str, ...]

    @property
    def matched_share(self) -> float:
        if self.total_length_km <= 0:
            return 0.0
        return self.matched_length_km / self.total_length_km


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _ref_set(value: Any) -> frozenset[str]:
    """Normaliza ``ref`` de OSM o ``road_ref`` de la capa a un conjunto."""
    if isinstance(value, (list, tuple, set)):
        texts = [str(item) for item in value]
    elif value is None:
        texts = []
    else:
        texts = [str(value)]

    refs: set[str] = set()
    for text in texts:
        for part in re.split(r"[;,/]", text):
            part = part.strip().upper()
            if part:
                refs.add(part)
    return frozenset(refs)


def _edge_geometry(
    G: nx.MultiDiGraph, u: int, v: int, attrs: Mapping[str, Any]
) -> LineString:
    geometry = attrs.get("geometry")
    if isinstance(geometry, str):
        geometry = wkt.loads(geometry)
    if geometry is not None and not geometry.is_empty:
        return geometry

    return LineString(
        [
            (float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
            (float(G.nodes[v]["x"]), float(G.nodes[v]["y"])),
        ]
    )


def _segment_label(row: Any) -> str:
    road_ref = str(row.get("road_ref") or "?")
    pk_start = _as_float(row.get("pk_start"))
    pk_end = _as_float(row.get("pk_end"))
    if pk_start is not None and pk_end is not None:
        return f"{road_ref} PK {pk_start:g}-{pk_end:g}"
    return road_ref


def _match_sort_key(match: TrafficMatch) -> tuple:
    """Orden determinista: cercanía, confianza, año y IMD conservador."""
    return (
        round(match.distance_m, 3),
        -CONFIDENCE_ORDER.get(match.confidence, 0),
        -(match.year or 0),
        -match.imd,
    )


def _build_edge_frame(G: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    records = [
        {
            "u": u,
            "v": v,
            "key": key,
            "refs": _ref_set(attrs.get("ref")),
            "length": float(attrs.get("length") or 0.0),
            "geometry": _edge_geometry(G, u, v, attrs),
        }
        for u, v, key, attrs in G.edges(keys=True, data=True)
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


def _candidate_indices(
    spatial_index, geometry, buffer_m: float
) -> Sequence[int]:
    """Índices de aristas a menos de ``buffer_m``; tolera versiones sin dwithin."""
    try:
        return list(
            spatial_index.query(
                geometry, predicate="dwithin", distance=buffer_m
            )
        )
    except TypeError:  # GeoPandas antiguo sin predicate="dwithin"
        return list(
            spatial_index.query(
                geometry.buffer(buffer_m), predicate="intersects"
            )
        )


def enrich_graph_with_traffic(
    G: nx.MultiDiGraph,
    segments: gpd.GeoDataFrame | None = None,
    *,
    buffer_m: float = MATCH_BUFFER_M,
) -> EnrichmentReport:
    """Asocia la capa medida a las aristas y escribe los campos del contrato.

    Modifica ``G`` y marca ``cycle_escape_scored = False``. El llamador debe
    ejecutar después ``score_graph_edges`` para recalcular Road Stress.
    """
    if buffer_m <= 0:
        raise ValueError("buffer_m debe ser positivo")

    if segments is None:
        segments = load_traffic_segments()

    if not isinstance(segments, gpd.GeoDataFrame):
        raise TrafficEnrichmentError("la capa de tráfico debe ser un GeoDataFrame")
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in segments.columns
    ]
    if missing_columns:
        raise TrafficEnrichmentError(
            "faltan columnas en la capa de tráfico: "
            + ", ".join(missing_columns)
        )

    edges = _build_edge_frame(G)
    total_edges = len(edges)
    total_length_km = round(
        float(edges["length"].sum()) / 1000.0, 1
    )
    total_segments = len(segments)

    if total_edges == 0:
        raise TrafficEnrichmentError("el grafo no tiene aristas")

    # La capa es la fuente de verdad: limpia valores medidos de una ejecución
    # anterior para que una arista que ya no casa no conserve IMD viejo.
    for _, _, attrs in G.edges(data=True):
        for key in (
            "imd",
            "heavy_pct",
            "traffic_source",
            "traffic_year",
            "traffic_confidence",
        ):
            attrs.pop(key, None)

    if total_segments == 0:
        return EnrichmentReport(
            matched_edges=0,
            total_edges=total_edges,
            matched_segments=0,
            total_segments=0,
            matched_length_km=0.0,
            total_length_km=total_length_km,
            sources=(),
            missing_segments=(),
        )

    utm_crs = edges.estimate_utm_crs() or "EPSG:32629"
    edges_projected = edges.to_crs(utm_crs)
    traffic_projected = segments.to_crs(utm_crs)
    spatial_index = edges_projected.sindex

    best: dict[tuple[int, int, int], TrafficMatch] = {}
    matched_segment_indices: set[int] = set()
    missing_segments: list[str] = []

    for segment_index, row in traffic_projected.iterrows():
        source = str(row.get("traffic_source") or "").strip().lower()
        imd = _as_float(row.get("imd"))
        refs = _ref_set(row.get("road_ref"))
        geometry = row.geometry

        if (
            source not in MEASURED_SOURCES
            or imd is None
            or imd <= 0
            or not refs
            or geometry is None
            or geometry.is_empty
        ):
            missing_segments.append(_segment_label(row))
            continue

        heavy_pct = _as_float(row.get("heavy_pct"))
        if heavy_pct is not None and not 0 <= heavy_pct <= 100:
            heavy_pct = None

        year_value = _as_float(row.get("traffic_year"))
        year = int(round(year_value)) if year_value is not None else None

        confidence = str(row.get("traffic_confidence") or "medium").lower()
        if confidence not in CONFIDENCE_ORDER:
            confidence = "medium"

        matched_this_segment = False
        for candidate in _candidate_indices(
            spatial_index, geometry, buffer_m
        ):
            edge = edges_projected.iloc[candidate]
            if not refs & edge["refs"]:
                continue

            distance = float(edge.geometry.distance(geometry))
            if distance > buffer_m:
                continue

            match = TrafficMatch(
                edge=(int(edge["u"]), int(edge["v"]), int(edge["key"])),
                distance_m=distance,
                imd=int(round(imd)),
                heavy_pct=round(heavy_pct, 2) if heavy_pct is not None else None,
                source=source,
                year=year,
                confidence=confidence,
                road_ref=str(row.get("road_ref") or "").strip().upper(),
            )

            current = best.get(match.edge)
            if current is None or _match_sort_key(match) < _match_sort_key(current):
                best[match.edge] = match

            matched_this_segment = True

        if matched_this_segment:
            matched_segment_indices.add(segment_index)
        else:
            missing_segments.append(_segment_label(row))

    matched_length_km = 0.0
    for (u, v, key), match in best.items():
        attrs = G[u][v][key]
        attrs["imd"] = match.imd
        attrs["heavy_pct"] = match.heavy_pct
        attrs["traffic_source"] = match.source
        attrs["traffic_year"] = match.year
        attrs["traffic_confidence"] = match.confidence
        try:
            matched_length_km += float(attrs.get("length") or 0.0)
        except (TypeError, ValueError):
            pass

    G.graph["cycle_escape_scored"] = False

    report = EnrichmentReport(
        matched_edges=len(best),
        total_edges=total_edges,
        matched_segments=len(matched_segment_indices),
        total_segments=total_segments,
        matched_length_km=round(matched_length_km / 1000.0, 1),
        total_length_km=total_length_km,
        sources=tuple(sorted({match.source for match in best.values()})),
        missing_segments=tuple(missing_segments),
    )

    logger.info(
        "Tráfico medido: %d/%d tramos, %d/%d aristas, %.1f/%.1f km (%.1f%%)",
        report.matched_segments,
        report.total_segments,
        report.matched_edges,
        report.total_edges,
        report.matched_length_km,
        report.total_length_km,
        report.matched_share * 100,
    )
    if report.missing_segments:
        preview = ", ".join(report.missing_segments[:4])
        logger.info(
            "%d tramos sin match (fuera de cobertura o sin ref): %s%s",
            len(report.missing_segments),
            preview,
            "..." if len(report.missing_segments) > 4 else "",
        )

    return report


__all__ = [
    "EnrichmentReport",
    "MATCH_BUFFER_M",
    "TrafficEnrichmentError",
    "TrafficMatch",
    "enrich_graph_with_traffic",
]
