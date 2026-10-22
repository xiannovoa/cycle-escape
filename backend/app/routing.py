"""Motor de routing: coste ponderado y candidatos de escape por dirección.

El coste de cada arista es::

    coste = longitud * (1 + lambda * road_stress / 100)

donde ``lambda`` crece con la aversión al tráfico del usuario. Con aversión 0
el camino es el más corto; con aversión alta acepta desvíos para evitar
carreteras estresantes. La velocidad media solo convierte distancia en tiempo:
no altera qué camino es el mejor.

Los destinos no los elige el usuario. Se generan nodos en un anillo de 8-12 km
alrededor del origen, repartidos en los 8 sectores del contrato (N, NE, E...).
Este módulo devuelve rutas candidatas; detectar el Escape Point y rankearlas
es responsabilidad de ``escape_point.py``.

El grafo debe estar sin proyectar (EPSG:4326, ``x`` = longitud, ``y`` =
latitud), tal como lo devuelve ``data_loader.get_graph``.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import networkx as nx
from pyproj import Transformer

from app.models import DIRECTIONS, Direction
from app.scoring import score_graph_edges

logger = logging.getLogger(__name__)

#: Anillo donde se buscan destinos candidatos.
RING_MIN_M = 8_000.0
RING_MAX_M = 12_000.0

#: Radios objetivo dentro del anillo, de interior a exterior.
RING_TARGETS_M = (9_000.0, 11_000.0)

DEFAULT_PER_SECTOR = 2
MAX_PER_SECTOR = 3

#: Aversión máxima: una arista con estrés 100 cuesta 4 veces su longitud.
LAMBDA_MAX = 3.0

DEFAULT_AVG_SPEED_KMH = 22.0

#: Si el origen queda más lejos que esto del nodo más cercano, no hay cobertura.
MAX_ORIGIN_SNAP_M = 1_000.0

WeightFn = Callable[[int, int, Mapping[str, Any]], float]


class RoutingError(RuntimeError):
    """Error base del motor de routing."""


class OriginOutsideCoverageError(RoutingError):
    """El origen no tiene ningún nodo del grafo lo bastante cerca."""


class NoCandidatesError(RoutingError):
    """No hay destinos candidatos o no son alcanzables."""


@dataclass(frozen=True)
class CandidateTarget:
    """Nodo del anillo elegido como destino de un corredor."""

    direction: Direction
    node: int
    lat: float
    lon: float
    ring_distance_km: float


@dataclass(frozen=True)
class PathEdge:
    """Arista recorrida, con todo lo necesario para pintarla y explicarla."""

    u: int
    v: int
    key: int
    length_m: float
    road_stress: float
    coordinates: tuple[tuple[float, float], ...]
    attrs: dict[str, Any]


@dataclass(frozen=True)
class CandidateRoute:
    """Ruta completa hacia un destino del anillo, antes de detectar el Escape Point."""

    direction: Direction
    target_node: int
    target_lat: float
    target_lon: float
    ring_distance_km: float
    distance_km: float
    time_min: float
    avg_speed_kmh: float
    weighted_cost: float
    avg_road_stress: float
    geometry: tuple[tuple[float, float], ...]
    edges: tuple[PathEdge, ...]


# --- Utilidades geográficas -----------------------------------------------


def utm_transformer(lat: float, lon: float) -> Transformer:
    """Transformador WGS84 -> UTM de la zona del origen (metros locales)."""
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(zone, 60))
    epsg = (32600 if lat >= 0 else 32700) + zone
    return Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)


def _project_nodes(
    G: nx.MultiDiGraph, lat: float, lon: float
) -> tuple[list[int], list[float], list[float], float, float]:
    """Proyecta todos los nodos y el origen a metros UTM."""
    transformer = utm_transformer(lat, lon)
    nodes = list(G.nodes)
    lons = [float(G.nodes[node]["x"]) for node in nodes]
    lats = [float(G.nodes[node]["y"]) for node in nodes]
    xs, ys = transformer.transform(lons, lats)
    origin_x, origin_y = transformer.transform(lon, lat)
    return nodes, list(xs), list(ys), origin_x, origin_y


def nearest_graph_node(
    G: nx.MultiDiGraph, lat: float, lon: float
) -> tuple[int, float]:
    """Nodo más cercano al origen y su distancia en metros."""
    nodes, xs, ys, origin_x, origin_y = _project_nodes(G, lat, lon)
    if not nodes:
        raise OriginOutsideCoverageError("el grafo está vacío")

    best_node, best_distance2 = nodes[0], math.inf
    for node, x, y in zip(nodes, xs, ys):
        distance2 = (x - origin_x) ** 2 + (y - origin_y) ** 2
        if distance2 < best_distance2:
            best_node, best_distance2 = node, distance2

    return best_node, math.sqrt(best_distance2)


def sector_for_bearing(bearing_deg: float) -> Direction:
    """Sector de 45 grados que contiene un rumbo (0 = norte, 90 = este)."""
    index = int(((bearing_deg + 22.5) % 360.0) // 45.0)
    return DIRECTIONS[index % len(DIRECTIONS)]


def _target_radii(per_sector: int) -> tuple[float, ...]:
    if per_sector <= 0:
        raise ValueError("per_sector debe ser positivo")
    if per_sector == 1:
        return (10_000.0,)
    if per_sector == 2:
        return RING_TARGETS_M
    return (8_500.0, 10_000.0, 11_500.0)


def select_candidate_targets(
    G: nx.MultiDiGraph,
    origin_lat: float,
    origin_lon: float,
    *,
    ring_min_m: float = RING_MIN_M,
    ring_max_m: float = RING_MAX_M,
    per_sector: int = DEFAULT_PER_SECTOR,
) -> list[CandidateTarget]:
    """Elige nodos del anillo, repartidos por los 8 sectores.

    Para cada sector se busca el nodo más cercano a cada radio objetivo. La
    elección es determinista: a igual distancia, gana el id de nodo menor.
    """
    if ring_min_m <= 0 or ring_max_m <= ring_min_m:
        raise ValueError("el anillo debe cumplir 0 < ring_min_m < ring_max_m")

    per_sector = min(per_sector, MAX_PER_SECTOR)
    radii = _target_radii(per_sector)

    nodes, xs, ys, origin_x, origin_y = _project_nodes(G, origin_lat, origin_lon)

    by_sector: dict[Direction, list[tuple[float, int]]] = {
        direction: [] for direction in DIRECTIONS
    }

    for node, x, y in zip(nodes, xs, ys):
        dx, dy = x - origin_x, y - origin_y
        distance = math.hypot(dx, dy)
        if not ring_min_m <= distance <= ring_max_m:
            continue

        bearing = math.degrees(math.atan2(dx, dy)) % 360.0
        by_sector[sector_for_bearing(bearing)].append((distance, node))

    selected: list[CandidateTarget] = []
    used: set[int] = set()

    for direction in DIRECTIONS:
        positions = by_sector[direction]
        if not positions:
            continue

        for radius in radii:
            available = [item for item in positions if item[1] not in used]
            if not available:
                break

            distance, node = min(
                available, key=lambda item: (abs(item[0] - radius), item[1])
            )
            used.add(node)
            selected.append(
                CandidateTarget(
                    direction=direction,
                    node=node,
                    lat=float(G.nodes[node]["y"]),
                    lon=float(G.nodes[node]["x"]),
                    ring_distance_km=round(distance / 1000.0, 1),
                )
            )

    return selected


# --- Coste y construcción de rutas ----------------------------------------


def lambda_for(traffic_aversion: float) -> float:
    """Convierte la aversión 0-1 en el ``lambda`` del coste."""
    if not 0.0 <= traffic_aversion <= 1.0:
        raise ValueError("traffic_aversion debe estar entre 0 y 1")
    return LAMBDA_MAX * traffic_aversion


def weight_function(lam: float) -> WeightFn:
    """Coste por arista: longitud penalizada por Road Stress.

    NetworkX pasa a la función de peso, en multigrafos, el diccionario de
    aristas paralelas. Se devuelve el mínimo, igual que hace NetworkX cuando
    el peso es el nombre de un atributo.
    """

    def weight(u: int, v: int, data: Mapping[str, Any]) -> float:
        if data and all(isinstance(attrs, Mapping) for attrs in data.values()):
            return min(weight(u, v, attrs) for attrs in data.values())

        length = float(data.get("length") or 0.0)
        stress = float(data.get("road_stress") or 0.0)
        return length * (1.0 + lam * stress / 100.0)

    return weight


def ensure_scored(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Garantiza que todas las aristas tienen Road Stress."""
    if not G.graph.get("cycle_escape_scored"):
        score_graph_edges(G)
    return G


def _min_weight_edge(
    G: nx.MultiDiGraph, u: int, v: int, weight: WeightFn
) -> tuple[int, Mapping[str, Any]]:
    """Entre aristas paralelas, la de menor coste."""
    edges = G[u][v]
    return min(edges.items(), key=lambda item: weight(u, v, item[1]))


def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _edge_coordinates(
    G: nx.MultiDiGraph, u: int, v: int, attrs: Mapping[str, Any]
) -> tuple[tuple[float, float], ...]:
    """Coordenadas de la arista orientadas siempre de ``u`` hacia ``v``."""
    ux, uy = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
    vx, vy = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])

    geometry = attrs.get("geometry")
    coords = getattr(geometry, "coords", None)
    if coords is not None:
        points = [(float(x), float(y)) for x, y in coords]
        if len(points) >= 2:
            if _dist2(points[0], (ux, uy)) > _dist2(points[-1], (ux, uy)):
                points.reverse()
            return tuple(points)

    return ((ux, uy), (vx, vy))


def _append_geometry(
    target: list[tuple[float, float]], coords: tuple[tuple[float, float], ...]
) -> None:
    for coord in coords:
        if not target or _dist2(target[-1], coord) > 1e-18:
            target.append(coord)


def _build_route(
    G: nx.MultiDiGraph,
    path: Sequence[int],
    target: CandidateTarget,
    weight: WeightFn,
    avg_speed_kmh: float,
) -> CandidateRoute:
    """Convierte una secuencia de nodos en una ruta con métricas y geometría."""
    edges: list[PathEdge] = []
    geometry: list[tuple[float, float]] = []
    total_length_m = 0.0
    total_cost = 0.0
    stress_length = 0.0

    for u, v in zip(path, path[1:]):
        key, attrs = _min_weight_edge(G, u, v, weight)
        length_m = float(attrs.get("length") or 0.0)
        road_stress = float(attrs.get("road_stress") or 0.0)
        coordinates = _edge_coordinates(G, u, v, attrs)

        edges.append(
            PathEdge(
                u=u,
                v=v,
                key=key,
                length_m=length_m,
                road_stress=road_stress,
                coordinates=coordinates,
                attrs=dict(attrs),
            )
        )
        _append_geometry(geometry, coordinates)
        total_length_m += length_m
        total_cost += weight(u, v, attrs)
        stress_length += road_stress * length_m

    distance_km = total_length_m / 1000.0
    avg_stress = stress_length / total_length_m if total_length_m > 0 else 0.0
    time_min = distance_km / avg_speed_kmh * 60.0 if avg_speed_kmh > 0 else 0.0

    return CandidateRoute(
        direction=target.direction,
        target_node=target.node,
        target_lat=target.lat,
        target_lon=target.lon,
        ring_distance_km=target.ring_distance_km,
        distance_km=round(distance_km, 3),
        time_min=round(time_min, 1),
        avg_speed_kmh=avg_speed_kmh,
        weighted_cost=round(total_cost, 1),
        avg_road_stress=round(avg_stress, 1),
        geometry=tuple(geometry),
        edges=tuple(edges),
    )


def route_candidates(
    G: nx.MultiDiGraph,
    origin_lat: float,
    origin_lon: float,
    *,
    avg_speed_kmh: float = DEFAULT_AVG_SPEED_KMH,
    traffic_aversion: float = 0.5,
    per_sector: int = DEFAULT_PER_SECTOR,
    ring_min_m: float = RING_MIN_M,
    ring_max_m: float = RING_MAX_M,
) -> list[CandidateRoute]:
    """Rutas candidatas desde un origen, una o dos por cada sector.

    Lanza ``OriginOutsideCoverageError`` si el origen cae lejos del grafo y
    ``NoCandidatesError`` si no hay anillo o ninguna ruta alcanzable.
    """
    if avg_speed_kmh <= 0:
        raise ValueError("avg_speed_kmh debe ser positivo")

    lam = lambda_for(traffic_aversion)
    ensure_scored(G)

    origin_node, snap_distance = nearest_graph_node(G, origin_lat, origin_lon)
    if snap_distance > MAX_ORIGIN_SNAP_M:
        raise OriginOutsideCoverageError(
            f"el origen está a {snap_distance / 1000:.1f} km del grafo más cercano"
        )

    targets = select_candidate_targets(
        G,
        origin_lat,
        origin_lon,
        ring_min_m=ring_min_m,
        ring_max_m=ring_max_m,
        per_sector=per_sector,
    )
    if not targets:
        raise NoCandidatesError(
            "no hay nodos del grafo en el anillo de candidatos"
        )

    weight = weight_function(lam)
    _, paths = nx.single_source_dijkstra(G, origin_node, weight=weight)

    routes: list[CandidateRoute] = []
    for target in targets:
        path = paths.get(target.node)
        if not path or len(path) < 2:
            logger.debug(
                "Destino %s inalcanzable desde el origen", target.node
            )
            continue
        routes.append(
            _build_route(G, path, target, weight, avg_speed_kmh)
        )

    if not routes:
        raise NoCandidatesError(
            "ningún destino del anillo es alcanzable desde el origen"
        )

    routes.sort(key=lambda route: (DIRECTIONS.index(route.direction), route.weighted_cost))
    return routes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.data_loader import SANTIAGO_CENTER, get_graph

    graph = get_graph()
    routes = route_candidates(
        graph, SANTIAGO_CENTER[0], SANTIAGO_CENTER[1], traffic_aversion=0.6
    )

    for route in routes:
        print(
            f"{route.direction:2s}  anillo {route.ring_distance_km:4.1f} km  "
            f"ruta {route.distance_km:5.1f} km  {route.time_min:4.1f} min  "
            f"estrés medio {route.avg_road_stress:4.1f}  "
            f"coste {route.weighted_cost:7.1f}"
        )


if __name__ == "__main__":
    main()
