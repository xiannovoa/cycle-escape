"""Detección del Escape Point y ranking de corredores.

El Escape Point no es el primer tramo con poco tráfico: es el primer punto
desde el que una **ventana hacia delante** se mantiene predominantemente
tranquila. Para cada punto de la ruta se analizan los siguientes kilómetros:

- QuietScore medio suficiente;
- mayoría de la distancia por debajo del umbral de estrés;
- ningún tramo de estrés extremo.

Si ninguna ventana cumple todo, se devuelve el mejor punto disponible marcado
como estimado (``valid=False``) y con un aviso, para no dejar la demo sin
resultado. El ranking combina tiempo hasta escapar y QuietScore posterior,
con pesos que dependen de ``route_preference``.

Los umbrales por defecto están calibrados con Santiago: ventana de 5 km,
QuietScore medio >= 70 y salida de zona urbana densa (<= 200 nodos del grafo
en 1 km). Son heurísticos y configurables; no pretenden ser universales.
"""

from __future__ import annotations

import logging
import math
import unicodedata
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

import networkx as nx

from app.models import DIRECTIONS, Direction
from app.routing import (
    CandidateRoute,
    NoCandidatesError,
    PathEdge,
    utm_transformer,
)

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_KM = 5.0
MIN_MEAN_QUIET = 70.0
MIN_QUIET_SHARE = 0.80
QUIET_STRESS_MAX = 40.0
#: Coincide con el rojo de la convención de colores de la interfaz.
EXTREME_STRESS = 75.0

#: Penalización de ranking para un Escape Point estimado (sin ventana válida).
FALLBACK_PENALTY = 15.0

#: Pesos (tiempo, tranquilidad) según la preferencia del usuario.
ROUTE_PREFERENCE_WEIGHTS: dict[str, tuple[float, float]] = {
    "direct": (0.7, 0.3),
    "balanced": (0.5, 0.5),
    "quiet": (0.3, 0.7),
}

DIRECTION_SLUGS: dict[str, str] = {
    "N": "norte",
    "NE": "noreste",
    "E": "este",
    "SE": "sureste",
    "S": "sur",
    "SW": "suroeste",
    "W": "oeste",
    "NW": "noroeste",
}


class EscapePointError(RuntimeError):
    """Error base de la detección del Escape Point."""


class NoSustainedQuietError(EscapePointError):
    """No hay ninguna ventana sostenida de calma."""


@dataclass(frozen=True)
class EscapeThresholds:
    """Umbrales heurísticos de la ventana de calma."""

    window_km: float = DEFAULT_WINDOW_KM
    min_mean_quiet: float = MIN_MEAN_QUIET
    min_quiet_share: float = MIN_QUIET_SHARE
    quiet_stress_max: float = QUIET_STRESS_MAX
    extreme_stress: float = EXTREME_STRESS
    #: Radio y nº de nodos del grafo por encima del cual se considera urbano.
    urban_radius_m: float = 1000.0
    max_urban_nodes: int | None = 200

    def __post_init__(self) -> None:
        if self.window_km <= 0:
            raise ValueError("window_km debe ser positivo")
        if not 0 <= self.min_mean_quiet <= 100:
            raise ValueError("min_mean_quiet debe estar entre 0 y 100")
        if not 0 <= self.min_quiet_share <= 1:
            raise ValueError("min_quiet_share debe estar entre 0 y 1")
        if not 0 <= self.quiet_stress_max <= 100:
            raise ValueError("quiet_stress_max debe estar entre 0 y 100")
        if not 0 <= self.extreme_stress <= 100:
            raise ValueError("extreme_stress debe estar entre 0 y 100")
        if self.quiet_stress_max >= self.extreme_stress:
            raise ValueError(
                "quiet_stress_max debe ser menor que extreme_stress"
            )
        if (
            self.max_urban_nodes is not None
            and self.max_urban_nodes < 0
        ):
            raise ValueError("max_urban_nodes no puede ser negativo")
        if self.urban_radius_m <= 0:
            raise ValueError("urban_radius_m debe ser positivo")


DEFAULT_THRESHOLDS = EscapeThresholds()


@dataclass(frozen=True)
class WindowStats:
    """Resumen de la ventana hacia delante desde un punto candidato."""

    covered_km: float
    mean_quiet_score: float
    quiet_share: float
    max_stress: float


@dataclass(frozen=True)
class EscapePointResult:
    """Punto de salida detectado (o estimado) sobre la ruta."""

    lat: float
    lon: float
    edge_index: int
    name: str | None
    valid: bool
    window: WindowStats
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EscapeRouteResult:
    """Corredor con Escape Point, métricas y posición en el ranking."""

    id: str
    direction: Direction
    escape_point: EscapePointResult
    escape_time_min: float
    distance_to_escape_km: float
    quiet_score: float
    avg_road_stress: float
    post_escape_stress: float
    ranking_score: float
    rank: int
    is_recommended: bool
    target_node: int
    target_lat: float
    target_lon: float
    ring_distance_km: float
    distance_km: float
    time_min: float
    avg_speed_kmh: float
    geometry: tuple[tuple[float, float], ...]
    edges: tuple[PathEdge, ...]
    warnings: tuple[str, ...] = ()


class NodeDensityIndex:
    """Índice espacial para contar nodos del grafo alrededor de un punto.

    Se usa como indicador genérico de urbanidad: en el centro de Santiago hay
    ~85-175 nodos en 500 m; en carretera, ~10-50. Es una heurística, no una
    frontera administrativa, y se puede desactivar con
    ``max_urban_nodes_500m=None``.
    """

    def __init__(self, G: nx.MultiDiGraph, cell_size_m: float = 500.0) -> None:
        if G.number_of_nodes() == 0:
            raise ValueError("el grafo no tiene nodos")
        if cell_size_m <= 0:
            raise ValueError("cell_size_m debe ser positivo")

        nodes = list(G.nodes)
        lons = [float(G.nodes[node]["x"]) for node in nodes]
        lats = [float(G.nodes[node]["y"]) for node in nodes]
        mean_lon = sum(lons) / len(lons)
        mean_lat = sum(lats) / len(lats)

        self._transformer = utm_transformer(mean_lat, mean_lon)
        self._cell_size = cell_size_m
        self._cells: dict[tuple[int, int], list[tuple[float, float]]] = {}

        xs, ys = self._transformer.transform(lons, lats)
        for x, y in zip(xs, ys):
            key = (math.floor(x / cell_size_m), math.floor(y / cell_size_m))
            self._cells.setdefault(key, []).append((float(x), float(y)))

    def count_within(
        self, lon: float, lat: float, radius_m: float = 500.0
    ) -> int:
        """Número de nodos del grafo a menos de ``radius_m`` del punto."""
        if radius_m <= 0:
            raise ValueError("radius_m debe ser positivo")

        x, y = self._transformer.transform(lon, lat)
        cell = self._cell_size
        min_cx = math.floor((x - radius_m) / cell)
        max_cx = math.floor((x + radius_m) / cell)
        min_cy = math.floor((y - radius_m) / cell)
        max_cy = math.floor((y + radius_m) / cell)
        radius2 = radius_m * radius_m

        count = 0
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                for px, py in self._cells.get((cx, cy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 <= radius2:
                        count += 1
        return count


# --- Utilidades ------------------------------------------------------------


def _cumulative_distances(
    edges: Sequence[PathEdge],
) -> tuple[list[float], list[float], float]:
    starts: list[float] = []
    ends: list[float] = []
    total = 0.0
    for edge in edges:
        starts.append(total)
        total += max(0.0, edge.length_m)
        ends.append(total)
    return starts, ends, total


def _usable_indices(edges: Sequence[PathEdge]) -> list[int]:
    return [index for index, edge in enumerate(edges) if edge.length_m > 0]


def _window_stats(
    edges: Sequence[PathEdge],
    starts: Sequence[float],
    ends: Sequence[float],
    total_length_m: float,
    index: int,
    thresholds: EscapeThresholds,
) -> WindowStats:
    """Estadísticas de la ventana que empieza en la arista ``index``."""
    start = starts[index]
    end = start + thresholds.window_km * 1000.0
    covered = min(total_length_m, end) - start

    if covered <= 0:
        return WindowStats(0.0, 0.0, 0.0, 0.0)

    weighted_quiet = 0.0
    quiet_length = 0.0
    max_stress = 0.0

    for j in range(index, len(edges)):
        if starts[j] >= end:
            break
        overlap = min(ends[j], end) - max(starts[j], start)
        if overlap <= 0:
            continue

        stress = max(0.0, min(100.0, edges[j].road_stress))
        weighted_quiet += (100.0 - stress) * overlap
        if stress <= thresholds.quiet_stress_max:
            quiet_length += overlap
        max_stress = max(max_stress, stress)

    return WindowStats(
        covered_km=covered / 1000.0,
        mean_quiet_score=weighted_quiet / covered,
        quiet_share=quiet_length / covered,
        max_stress=max_stress,
    )


def _is_valid_window(
    stats: WindowStats, thresholds: EscapeThresholds
) -> bool:
    return (
        stats.covered_km >= thresholds.window_km - 1e-6
        and stats.mean_quiet_score >= thresholds.min_mean_quiet
        and stats.quiet_share >= thresholds.min_quiet_share
        and stats.max_stress < thresholds.extreme_stress
    )


def _fallback_score(stats: WindowStats) -> float:
    """Cuanto más tranquila y completa la ventana, mejor candidato de reserva."""
    return (
        stats.mean_quiet_score
        + 100.0 * stats.quiet_share
        - stats.max_stress
    )


def _point_name(edge: PathEdge) -> str | None:
    for key in ("name", "ref"):
        value = edge.attrs.get(key)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value:
            text = str(value).strip()
            if text:
                return text
    return None


def _make_point(
    route: CandidateRoute,
    index: int,
    valid: bool,
    stats: WindowStats,
    warnings: Iterable[str] = (),
) -> EscapePointResult:
    edge = route.edges[index]
    lon, lat = edge.coordinates[0]
    return EscapePointResult(
        lat=round(lat, 6),
        lon=round(lon, 6),
        edge_index=index,
        name=_point_name(edge),
        valid=valid,
        window=stats,
        warnings=tuple(warnings),
    )


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    slug: list[str] = []
    for char in without_accents.lower():
        if char.isalnum():
            slug.append(char)
        elif slug and slug[-1] != "-":
            slug.append("-")
    return "".join(slug).strip("-")[:48].strip("-")


def _route_id(direction: Direction, name: str | None) -> str:
    direction_slug = DIRECTION_SLUGS[direction]
    name_slug = _slugify(name) if name else ""
    return f"{direction_slug}-{name_slug}" if name_slug else direction_slug


def _post_escape_metrics(
    route: CandidateRoute, index: int
) -> tuple[float, float]:
    """Estrés medio y QuietScore de la red posterior al Escape Point."""
    edges = route.edges[index:]
    total_length = sum(max(0.0, edge.length_m) for edge in edges)
    if total_length <= 0:
        return 0.0, 100.0

    stress = sum(edge.road_stress * edge.length_m for edge in edges) / total_length
    return round(stress, 1), round(100.0 - stress, 1)


def _avg_road_stress(route: CandidateRoute) -> float:
    total_length = sum(max(0.0, edge.length_m) for edge in route.edges)
    if total_length <= 0:
        return 0.0
    return round(
        sum(edge.road_stress * edge.length_m for edge in route.edges)
        / total_length,
        1,
    )


# --- API pública -----------------------------------------------------------


def detect_escape_point(
    route: CandidateRoute,
    thresholds: EscapeThresholds = DEFAULT_THRESHOLDS,
    *,
    allow_fallback: bool = True,
    density_index: NodeDensityIndex | None = None,
) -> EscapePointResult:
    """Primer punto desde el que la ventana siguiente es sostenidamente tranquila.

    Si se pasa ``density_index``, se descartan los puntos que siguen en una
    zona urbana densa, aunque la ventana de estrés sea tranquila.
    """
    edges = route.edges
    if not edges:
        raise ValueError("la ruta no tiene aristas")

    usable = _usable_indices(edges)
    if not usable:
        raise ValueError("la ruta no tiene longitud positiva")

    starts, ends, total_length_m = _cumulative_distances(edges)

    for index in usable:
        if total_length_m - starts[index] < thresholds.window_km * 1000.0 - 1e-6:
            break  # a partir de aquí no queda ventana completa

        stats = _window_stats(
            edges, starts, ends, total_length_m, index, thresholds
        )
        if not _is_valid_window(stats, thresholds):
            continue

        if (
            density_index is not None
            and thresholds.max_urban_nodes is not None
        ):
            lon, lat = edges[index].coordinates[0]
            density = density_index.count_within(
                lon, lat, thresholds.urban_radius_m
            )
            if density > thresholds.max_urban_nodes:
                continue

        return _make_point(route, index, True, stats)

    if not allow_fallback:
        raise NoSustainedQuietError(
            f"ningún punto mantiene {thresholds.window_km:g} km de calma"
        )

    # Reserva: el punto con la mejor ventana disponible, aunque no sea completa.
    candidates = [
        index
        for index in usable
        if total_length_m - starts[index]
        >= min(thresholds.window_km * 1000.0, total_length_m * 0.5)
    ]
    if not candidates:
        candidates = usable[:1]

    scored = {
        index: _window_stats(
            edges, starts, ends, total_length_m, index, thresholds
        )
        for index in candidates
    }
    best_index = max(scored, key=lambda index: (_fallback_score(scored[index]), -index))

    warnings = [
        "No se encontró una ventana sostenida de calma; Escape Point estimado."
    ]
    if total_length_m < thresholds.window_km * 1000.0:
        warnings.append(
            f"La ruta es más corta que la ventana de calma "
            f"({thresholds.window_km:g} km)."
        )

    logger.debug(
        "Escape Point estimado en arista %s de %s", best_index, route.direction
    )
    return _make_point(
        route, best_index, False, scored[best_index], warnings
    )


def rank_escape_routes(
    routes: Sequence[CandidateRoute],
    *,
    route_preference: str = "balanced",
    traffic_lambda: float | None = None,
    max_routes: int = 5,
    thresholds: EscapeThresholds = DEFAULT_THRESHOLDS,
    allow_fallback: bool = True,
    graph: nx.MultiDiGraph | None = None,
) -> list[EscapeRouteResult]:
    """Detecta el Escape Point de cada ruta y devuelve los mejores corredores.

    Se elige primero la mejor ruta de cada dirección y después se ordenan las
    direcciones. El tiempo se normaliza entre candidatos y se combina con el
    QuietScore posterior.

    ``traffic_lambda`` (0 = directo, 1 = tranquilo) define el peso continuo.
    Si no se envía, se usan los pesos discretos de ``route_preference`` para
    mantener compatibilidad con clientes antiguos. Si se pasa ``graph``, se
    exige además que el Escape Point haya salido de una zona urbana densa.
    """
    if not routes:
        raise NoCandidatesError("no hay rutas candidatas que rankear")
    if max_routes < 1:
        raise ValueError("max_routes debe ser positivo")

    if traffic_lambda is not None:
        if not 0.0 <= traffic_lambda <= 1.0:
            raise ValueError("traffic_lambda debe estar entre 0 y 1")
        weight_time = 1.0 - traffic_lambda
        weight_quiet = traffic_lambda
    else:
        weights = ROUTE_PREFERENCE_WEIGHTS.get(route_preference)
        if weights is None:
            raise ValueError(
                "route_preference debe ser direct, balanced o quiet"
            )
        weight_time, weight_quiet = weights

    density_index = (
        NodeDensityIndex(
            graph, cell_size_m=max(250.0, thresholds.urban_radius_m)
        )
        if graph is not None
        else None
    )

    scored: list[EscapeRouteResult] = []
    for route in routes:
        point = detect_escape_point(
            route,
            thresholds,
            allow_fallback=allow_fallback,
            density_index=density_index,
        )
        starts, _ends, _total = _cumulative_distances(route.edges)
        distance_to_escape_km = starts[point.edge_index] / 1000.0
        escape_time_min = (
            distance_to_escape_km / route.avg_speed_kmh * 60.0
            if route.avg_speed_kmh > 0
            else 0.0
        )
        post_stress, quiet_score = _post_escape_metrics(
            route, point.edge_index
        )

        scored.append(
            EscapeRouteResult(
                id=_route_id(route.direction, point.name),
                direction=route.direction,
                escape_point=point,
                escape_time_min=round(escape_time_min, 1),
                distance_to_escape_km=round(distance_to_escape_km, 2),
                quiet_score=quiet_score,
                avg_road_stress=_avg_road_stress(route),
                post_escape_stress=post_stress,
                ranking_score=0.0,
                rank=0,
                is_recommended=False,
                target_node=route.target_node,
                target_lat=route.target_lat,
                target_lon=route.target_lon,
                ring_distance_km=route.ring_distance_km,
                distance_km=route.distance_km,
                time_min=route.time_min,
                avg_speed_kmh=route.avg_speed_kmh,
                geometry=route.geometry,
                edges=route.edges,
                warnings=point.warnings,
            )
        )

    times = [result.escape_time_min for result in scored]
    min_time, max_time = min(times), max(times)
    time_range = max_time - min_time

    def time_score(value: float) -> float:
        if time_range <= 0:
            return 100.0
        return 100.0 * (max_time - value) / time_range

    ranked_input: list[EscapeRouteResult] = []
    for result in scored:
        score = (
            weight_time * time_score(result.escape_time_min)
            + weight_quiet * result.quiet_score
            - (0.0 if result.escape_point.valid else FALLBACK_PENALTY)
        )
        ranked_input.append(replace(result, ranking_score=round(score, 1)))

    # Mejor candidato por dirección. Un Escape Point válido siempre gana a uno
    # estimado, aunque el estimado tenga un tiempo de salida menor.
    best_by_direction: dict[Direction, EscapeRouteResult] = {}
    for result in ranked_input:
        current = best_by_direction.get(result.direction)
        if current is None or (
            result.escape_point.valid,
            result.ranking_score,
            -result.escape_time_min,
            result.id,
        ) > (
            current.escape_point.valid,
            current.ranking_score,
            -current.escape_time_min,
            current.id,
        ):
            best_by_direction[result.direction] = result

    ordered = sorted(
        best_by_direction.values(),
        key=lambda result: (
            not result.escape_point.valid,
            -result.ranking_score,
            result.escape_time_min,
            DIRECTIONS.index(result.direction),
        ),
    )[:max_routes]

    return [
        replace(result, rank=position, is_recommended=(position == 1))
        for position, result in enumerate(ordered, start=1)
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.graph_loader import SANTIAGO_CENTER, get_graph
    from app.routing import route_candidates

    graph = get_graph()
    candidates = route_candidates(
        graph, SANTIAGO_CENTER[0], SANTIAGO_CENTER[1], traffic_aversion=0.6
    )
    routes = rank_escape_routes(candidates, graph=graph)

    for route in routes:
        marker = "*" if route.is_recommended else " "
        valid = "ok" if route.escape_point.valid else "estimado"
        print(
            f"{marker} {route.rank}. {route.id:28s} {route.direction:2s}  "
            f"salida {route.distance_to_escape_km:4.1f} km / "
            f"{route.escape_time_min:4.1f} min  "
            f"quiet {route.quiet_score:4.1f}  "
            f"estrés ruta {route.avg_road_stress:4.1f}  ({valid})"
        )


if __name__ == "__main__":
    main()
