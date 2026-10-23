"""Road Stress y QuietScore por arista.

Road Stress es una **estimación interpretable** (0-100, alto = peor) de lo
incómoda que puede resultar una carretera para un ciclista de carretera. No es
un "Safety Score": no certifica seguridad viaria.

La fórmula combina cinco señales de OSM con pesos fijos y explicables:

- clase de vía (40 %): exposición estructural;
- velocidad (25 %): a más velocidad, más estrés;
- vehículos pesados (20 %): porcentaje medido o prior por clase de vía;
- carriles (8 %): más carriles, más exposición;
- superficie (7 %): el asfalto es lo deseable para una bici de carretera.

Cuando hay aforo medido (``imd`` + ``traffic_source`` de Xunta o MITMA), el
resultado se mezcla al 50 % con el estrés del tráfico real. Sin aforo se usa
solo OSM y se marca ``osm_estimate``: **la ausencia de medición nunca se trata
como tráfico cero**, se estima con un prior no nulo.

QuietScore es la transformación de cara al usuario: ``100 - road_stress``.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

import networkx as nx

from app.models import TrafficConfidence, TrafficSource

logger = logging.getLogger(__name__)

# --- Pesos y escalas -------------------------------------------------------

#: Pesos de la estimación base. Suman 1.0.
W_CLASS = 0.40
W_SPEED = 0.25
W_HEAVY = 0.20
W_LANES = 0.08
W_SURFACE = 0.07

#: Peso del tráfico medido al mezclarse con la estimación base.
MEASURED_WEIGHT = 0.50
#: Dentro del bloque medido: IMD manda sobre el porcentaje de pesados.
W_IMD = 0.75
W_MEASURED_HEAVY = 0.25

#: Estrés por clase de vía (0-100).
HIGHWAY_STRESS: dict[str, float] = {
    "trunk": 72.0,
    "trunk_link": 60.0,
    "primary": 62.0,
    "primary_link": 52.0,
    "secondary": 48.0,
    "secondary_link": 42.0,
    "tertiary": 34.0,
    "tertiary_link": 30.0,
    "unclassified": 27.0,
    "residential": 20.0,
    "living_street": 12.0,
    "service": 14.0,
    "track": 24.0,
    "cycleway": 4.0,
    "path": 18.0,
    "footway": 22.0,
    "pedestrian": 15.0,
}
DEFAULT_HIGHWAY_STRESS = 35.0

#: Velocidad asumida cuando OSM no la etiqueta (km/h).
DEFAULT_MAXSPEED_KMH: dict[str, float] = {
    "trunk": 90.0,
    "trunk_link": 80.0,
    "primary": 90.0,
    "primary_link": 80.0,
    "secondary": 70.0,
    "secondary_link": 60.0,
    "tertiary": 60.0,
    "tertiary_link": 50.0,
    "unclassified": 50.0,
    "residential": 30.0,
    "living_street": 20.0,
    "service": 20.0,
    "track": 30.0,
    "cycleway": 15.0,
    "path": 15.0,
    "pedestrian": 10.0,
}
DEFAULT_MAXSPEED_FALLBACK = 50.0

#: Carriles asumidos cuando OSM no los etiqueta.
DEFAULT_LANES: dict[str, int] = {
    "trunk": 2,
    "trunk_link": 2,
    "primary": 2,
    "primary_link": 2,
    "secondary": 2,
    "secondary_link": 2,
    "tertiary": 1,
    "tertiary_link": 1,
    "unclassified": 1,
    "residential": 1,
    "living_street": 1,
    "service": 1,
    "track": 1,
    "cycleway": 1,
    "path": 1,
}
DEFAULT_LANES_FALLBACK = 1

#: Prior de pesados (%) cuando no hay medición. No es un dato medido.
DEFAULT_HEAVY_PCT: dict[str, float] = {
    "trunk": 12.0,
    "trunk_link": 10.0,
    "primary": 8.0,
    "primary_link": 8.0,
    "secondary": 6.0,
    "secondary_link": 6.0,
    "tertiary": 3.0,
    "tertiary_link": 3.0,
    "unclassified": 3.0,
    "residential": 1.0,
    "living_street": 0.5,
    "service": 1.0,
    "track": 2.0,
    "cycleway": 0.0,
    "path": 0.0,
}
DEFAULT_HEAVY_PCT_FALLBACK = 3.0

#: Estrés por superficie (0-100). Desconocida = 10, no 0.
SURFACE_STRESS: dict[str, float] = {
    "asphalt": 0.0,
    "paved": 2.0,
    "chipseal": 2.0,
    "concrete": 5.0,
    "metal": 10.0,
    "paving_stones": 18.0,
    "compacted": 28.0,
    "cobblestone": 35.0,
    "sett": 35.0,
    "wood": 40.0,
    "fine_gravel": 42.0,
    "gravel": 48.0,
    "unpaved": 60.0,
    "dirt": 60.0,
    "earth": 62.0,
    "ground": 62.0,
    "grass": 65.0,
    "sand": 70.0,
}
DEFAULT_SURFACE_STRESS = 10.0

#: Valores de ``cycleway:*`` que indican infraestructura segregada o carril bici.
CYCLEWAY_TRACK_VALUES = frozenset({"track", "opposite_track"})
CYCLEWAY_LANE_VALUES = frozenset(
    {"lane", "opposite_lane", "shared_lane", "share_busway"}
)
CYCLEWAY_TAGS = ("cycleway", "cycleway:both", "cycleway:left", "cycleway:right")

MEASURED_SOURCES = frozenset({"xunta", "mitma"})
CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})

MAX_BIKE_BONUS = 15.0


@dataclass(frozen=True)
class EdgeScore:
    """Resultado del scoring de una arista, con componentes explicables."""

    road_stress: float
    quiet_score: float
    traffic_source: TrafficSource
    traffic_confidence: TrafficConfidence
    components: dict[str, float]


# --- Normalización de atributos OSM ---------------------------------------


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _text(value: Any) -> str | None:
    value = _first(value)
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _as_float(value: Any) -> float | None:
    value = _first(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(round(number))


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _highway(attrs: Mapping[str, Any]) -> str:
    return _text(attrs.get("highway")) or "desconocido"


def parse_maxspeed(attrs: Mapping[str, Any]) -> float | None:
    """Extrae la velocidad en km/h de ``maxspeed`` o sus variantes.

    Admite ``"50"``, ``"50 km/h"``, ``"30 mph"``, listas y ``walk``/``none``.
    Devuelve ``None`` si no hay ningún valor utilizable.
    """
    for key in ("maxspeed", "maxspeed:forward", "maxspeed:backward"):
        raw = _first(attrs.get(key))
        if raw is None:
            continue

        text = str(raw).strip().lower()
        if text in {"walk", "foot"}:
            return 7.0
        if text in {"none", "unlimited"}:
            return 130.0

        match = re.search(r"(\d+(?:[.,]\d+)?)", text)
        if match is None:
            continue

        speed = float(match.group(1).replace(",", "."))
        if "mph" in text:
            speed *= 1.60934
        if speed > 0:
            return speed

    return None


def resolve_maxspeed(attrs: Mapping[str, Any]) -> float:
    """Velocidad efectiva: la etiquetada o, si falta, la típica de su clase."""
    explicit = parse_maxspeed(attrs)
    if explicit is not None:
        return explicit
    return DEFAULT_MAXSPEED_KMH.get(_highway(attrs), DEFAULT_MAXSPEED_FALLBACK)


def parse_lanes(attrs: Mapping[str, Any]) -> int | None:
    """Carriles totales si OSM los etiqueta, sumando sentido si hace falta."""
    lanes = _as_int(attrs.get("lanes"))
    if lanes is not None and lanes > 0:
        return lanes

    forward = _as_int(attrs.get("lanes:forward"))
    backward = _as_int(attrs.get("lanes:backward"))
    if forward is not None or backward is not None:
        return max(1, (forward or 0) + (backward or 0))

    return None


def resolve_lanes(attrs: Mapping[str, Any]) -> int:
    """Carriles efectivos: los etiquetados o el valor típico de su clase."""
    explicit = parse_lanes(attrs)
    if explicit is not None:
        return explicit
    return DEFAULT_LANES.get(_highway(attrs), DEFAULT_LANES_FALLBACK)


def parse_surface(attrs: Mapping[str, Any]) -> str | None:
    return _text(attrs.get("surface"))


def resolve_heavy_pct(attrs: Mapping[str, Any]) -> float:
    """Porcentaje de pesados medido o, si no hay, un prior por clase de vía."""
    measured = _as_float(attrs.get("heavy_pct"))
    if measured is not None and measured >= 0:
        return measured
    return DEFAULT_HEAVY_PCT.get(_highway(attrs), DEFAULT_HEAVY_PCT_FALLBACK)


# --- Componentes del estrés ------------------------------------------------


def _speed_stress(speed_kmh: float) -> float:
    return _clamp((speed_kmh - 20.0) * 1.2)


def _lane_stress(lanes: int) -> float:
    return _clamp((lanes - 1) * 20.0, 0.0, 80.0)


def _heavy_stress(heavy_pct: float) -> float:
    return _clamp(heavy_pct * 5.0)


def _surface_stress(surface: str | None) -> float:
    if surface is None:
        return DEFAULT_SURFACE_STRESS
    return SURFACE_STRESS.get(surface, DEFAULT_SURFACE_STRESS)


def _bike_bonus(attrs: Mapping[str, Any], highway: str) -> float:
    """Descuento por infraestructura ciclista o arcén. Acotado a 15 puntos."""
    bonus = 0.0

    if highway == "cycleway":
        bonus += 15.0
    else:
        cycleway_values = {
            _text(attrs.get(tag)) for tag in CYCLEWAY_TAGS if attrs.get(tag)
        }
        if cycleway_values & CYCLEWAY_TRACK_VALUES:
            bonus += 12.0
        elif cycleway_values & CYCLEWAY_LANE_VALUES:
            bonus += 8.0

        if _text(attrs.get("bicycle")) == "designated":
            bonus += 3.0

        shoulder_values = {
            _text(value)
            for value in (
                attrs.get("shoulder"),
                attrs.get("shoulder:right"),
                attrs.get("shoulder:left"),
            )
            if value is not None
        }
        if shoulder_values & {"yes", "both", "right", "left"}:
            bonus += 3.0

    return min(bonus, MAX_BIKE_BONUS)


def _imd_stress(imd: float) -> float:
    """Estrés del volumen medido, en escala logarítmica."""
    return _clamp(38.0 * math.log10(max(imd, 10.0)) - 76.0)


def _osm_richness(attrs: Mapping[str, Any]) -> int:
    """Cuántas señales clave vienen etiquetadas explícitamente en OSM."""
    explicit = (
        parse_maxspeed(attrs) is not None,
        parse_lanes(attrs) is not None,
        parse_surface(attrs) is not None,
    )
    return sum(explicit)


def _traffic_provenance(
    attrs: Mapping[str, Any], measured: bool
) -> tuple[TrafficSource, TrafficConfidence]:
    source = _text(attrs.get("traffic_source"))

    if measured and source in MEASURED_SOURCES:
        confidence = _text(attrs.get("traffic_confidence"))
        if confidence not in CONFIDENCE_VALUES:
            confidence = "medium"
        return source, confidence  # type: ignore[return-value]

    return "osm_estimate", ("medium" if _osm_richness(attrs) >= 2 else "low")


# --- API pública -----------------------------------------------------------


def osm_road_stress(attrs: Mapping[str, Any]) -> float:
    """Road Stress 0-100 usando solo atributos de OSM (sin aforo medido)."""
    highway = _highway(attrs)
    class_stress = HIGHWAY_STRESS.get(highway, DEFAULT_HIGHWAY_STRESS)
    speed_stress = _speed_stress(resolve_maxspeed(attrs))
    lane_stress = _lane_stress(resolve_lanes(attrs))
    heavy_stress = _heavy_stress(resolve_heavy_pct(attrs))
    surface_stress = _surface_stress(parse_surface(attrs))

    base = (
        W_CLASS * class_stress
        + W_SPEED * speed_stress
        + W_HEAVY * heavy_stress
        + W_LANES * lane_stress
        + W_SURFACE * surface_stress
    )
    bonus = _bike_bonus(attrs, highway)
    return round(_clamp(base - bonus), 1)


def measured_traffic_stress(
    imd: float, heavy_pct: float | None = None
) -> float:
    """Estrés derivado de un aforo medido (IMD y % de pesados).

    Si falta el porcentaje de pesados se usa el prior por defecto, nunca 0:
    no medir pesados no significa que no haya pesados.
    """
    if heavy_pct is None:
        heavy_pct = DEFAULT_HEAVY_PCT_FALLBACK
    return round(
        _clamp(W_IMD * _imd_stress(imd) + W_MEASURED_HEAVY * _heavy_stress(heavy_pct)),
        1,
    )


def quiet_from_stress(road_stress: float) -> float:
    """QuietScore 0-100: alto = tranquilo."""
    return round(_clamp(100.0 - road_stress), 1)


def _is_measured(attrs: Mapping[str, Any]) -> bool:
    """True solo si hay IMD y una fuente medida reconocida."""
    imd = _as_float(attrs.get("imd"))
    return (
        imd is not None
        and imd >= 0
        and _text(attrs.get("traffic_source")) in MEASURED_SOURCES
    )


def score_edge(attrs: Mapping[str, Any]) -> EdgeScore:
    """Calcula Road Stress, QuietScore y procedencia de datos de una arista."""
    base = osm_road_stress(attrs)

    imd = _as_float(attrs.get("imd"))
    measured = _is_measured(attrs)

    components: dict[str, float] = {
        "osm": base,
        "measured": 0.0,
        "bike_bonus": _bike_bonus(attrs, _highway(attrs)),
    }

    if measured:
        heavy_pct = resolve_heavy_pct(attrs)
        traffic_stress = measured_traffic_stress(imd, heavy_pct)
        stress = (
            (1.0 - MEASURED_WEIGHT) * base + MEASURED_WEIGHT * traffic_stress
        )
        components["measured"] = traffic_stress
    else:
        # IMD sin fuente medible: se ignora y se usa solo OSM.
        stress = base

    stress = round(_clamp(stress), 1)
    traffic_source, traffic_confidence = _traffic_provenance(attrs, measured)

    return EdgeScore(
        road_stress=stress,
        quiet_score=quiet_from_stress(stress),
        traffic_source=traffic_source,
        traffic_confidence=traffic_confidence,
        components=components,
    )


def score_graph_edges(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Anota todas las aristas con ``road_stress``, ``quiet_score`` y procedencia.

    Modifica el grafo recibido y lo devuelve. No escribe ``imd`` ni
    ``heavy_pct``: esos campos solo pueden venir del enriquecimiento de Eva.
    """
    orphan_imd = 0

    for _, _, attrs in G.edges(data=True):
        if _as_float(attrs.get("imd")) is not None and not _is_measured(attrs):
            orphan_imd += 1

        result = score_edge(attrs)
        attrs["road_stress"] = result.road_stress
        attrs["quiet_score"] = result.quiet_score
        attrs["traffic_source"] = result.traffic_source
        attrs["traffic_confidence"] = result.traffic_confidence

    if orphan_imd:
        logger.warning(
            "%d aristas tenían imd sin traffic_source medido; se ignoró el aforo",
            orphan_imd,
        )

    G.graph["cycle_escape_scored"] = True
    return G


__all__ = [
    "EdgeScore",
    "HIGHWAY_STRESS",
    "MEASURED_SOURCES",
    "quiet_from_stress",
    "measured_traffic_stress",
    "osm_road_stress",
    "parse_lanes",
    "parse_maxspeed",
    "parse_surface",
    "resolve_heavy_pct",
    "resolve_lanes",
    "resolve_maxspeed",
    "score_edge",
    "score_graph_edges",
]
