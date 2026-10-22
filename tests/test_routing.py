"""Tests del motor de routing y de los candidatos por dirección."""

from __future__ import annotations

import math

import networkx as nx
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

from app.data_loader import SANTIAGO_CENTER, cache_path, get_graph
from app.models import DIRECTIONS
from app.routing import (
    MAX_ORIGIN_SNAP_M,
    NoCandidatesError,
    OriginOutsideCoverageError,
    lambda_for,
    nearest_graph_node,
    route_candidates,
    sector_for_bearing,
    select_candidate_targets,
    weight_function,
)


# --- Utilidades para construir grafos sintéticos --------------------------


def _transformers(lat: float, lon: float) -> tuple[Transformer, Transformer]:
    zone = int((lon + 180.0) // 6.0) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    forward = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    inverse = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return forward, inverse


def offset(lat: float, lon: float, bearing_deg: float, distance_m: float):
    """Punto a una distancia y rumbo dados (0 = norte, 90 = este)."""
    forward, inverse = _transformers(lat, lon)
    x, y = forward.transform(lon, lat)
    radians = math.radians(bearing_deg)
    x += distance_m * math.sin(radians)
    y += distance_m * math.cos(radians)
    lon2, lat2 = inverse.transform(x, y)
    return lat2, lon2


def add_node(G: nx.MultiDiGraph, node: int, lat: float, lon: float) -> None:
    G.add_node(node, x=lon, y=lat)


def add_road(
    G: nx.MultiDiGraph,
    u: int,
    v: int,
    length_m: float,
    *,
    road_stress: float | None = None,
    key: int = 0,
    geometry=None,
) -> None:
    attrs = {
        "length": float(length_m),
        "highway": "tertiary",
        "maxspeed": "60",
        "lanes": "1",
        "surface": "asphalt",
    }
    if road_stress is not None:
        attrs["road_stress"] = float(road_stress)
    if geometry is not None:
        attrs["geometry"] = geometry
    G.add_edge(u, v, key=key, **attrs)


def build_ring_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    add_node(G, 1, *SANTIAGO_CENTER)

    node = 2
    for index, _direction in enumerate(DIRECTIONS):
        bearing = index * 45.0
        for distance in (9_000.0, 11_000.0):
            lat, lon = offset(*SANTIAGO_CENTER, bearing, distance)
            add_node(G, node, lat, lon)
            add_road(G, 1, node, distance)
            node += 1

    return G


def build_two_path_graph() -> nx.MultiDiGraph:
    """Origen al oeste, destino a 10 km. Ruta A corta y estresada; B larga y quieta."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.graph["cycle_escape_scored"] = True

    add_node(G, 1, *SANTIAGO_CENTER)  # origen

    # Ruta A: recta hacia el este, 10 km, 90 de estrés.
    add_node(G, 2, *offset(*SANTIAGO_CENTER, 90, 3_000))
    add_node(G, 3, *offset(*SANTIAGO_CENTER, 90, 7_000))
    add_node(G, 4, *offset(*SANTIAGO_CENTER, 90, 10_000))  # destino
    add_road(G, 1, 2, 3_000, road_stress=90)
    add_road(G, 2, 3, 4_000, road_stress=90)
    add_road(G, 3, 4, 3_000, road_stress=90)

    # Ruta B: rodeo por el norte, 12 km, 10 de estrés.
    add_node(G, 5, *offset(*SANTIAGO_CENTER, 0, 3_000))
    add_node(G, 6, *offset(*SANTIAGO_CENTER, 0, 5_000))
    add_node(G, 7, *offset(*SANTIAGO_CENTER, 0, 6_000))
    add_road(G, 1, 5, 2_500, road_stress=10)
    add_road(G, 5, 6, 2_500, road_stress=10)
    add_road(G, 6, 7, 3_000, road_stress=10)
    add_road(G, 7, 4, 4_000, road_stress=10)

    return G


# --- Sectores y coste -----------------------------------------------------


@pytest.mark.parametrize(
    ("bearing", "expected"),
    [
        (0, "N"),
        (22.4, "N"),
        (22.5, "NE"),
        (45, "NE"),
        (67.5, "E"),
        (90, "E"),
        (180, "S"),
        (270, "W"),
        (337.4, "NW"),
        (337.5, "N"),
        (359, "N"),
        (-10, "N"),
    ],
)
def test_sector_for_bearing(bearing: float, expected: str) -> None:
    assert sector_for_bearing(bearing) == expected


def test_lambda_for() -> None:
    assert lambda_for(0) == 0
    assert lambda_for(0.5) == pytest.approx(1.5)
    assert lambda_for(1) == pytest.approx(3.0)


@pytest.mark.parametrize("aversion", [-0.01, 1.01])
def test_lambda_for_rejects_out_of_range(aversion: float) -> None:
    with pytest.raises(ValueError):
        lambda_for(aversion)


def test_weight_function_penalizes_stress() -> None:
    weight = weight_function(2.0)

    assert weight(0, 1, {"length": 1000, "road_stress": 0}) == 1000
    assert weight(0, 1, {"length": 1000, "road_stress": 50}) == pytest.approx(2000)
    assert weight(0, 1, {"length": 1000, "road_stress": 100}) == pytest.approx(3000)
    assert weight(0, 1, {}) == 0


# --- Selección de candidatos ----------------------------------------------


def test_select_candidates_covers_eight_sectors() -> None:
    targets = select_candidate_targets(build_ring_graph(), *SANTIAGO_CENTER)

    assert len(targets) == 16
    assert {target.direction for target in targets} == set(DIRECTIONS)
    assert {round(target.ring_distance_km) for target in targets} == {9, 11}
    assert all(8.9 <= target.ring_distance_km <= 11.1 for target in targets)


def test_select_candidates_is_deterministic() -> None:
    first = select_candidate_targets(build_ring_graph(), *SANTIAGO_CENTER)
    second = select_candidate_targets(build_ring_graph(), *SANTIAGO_CENTER)

    assert first == second


def test_select_candidates_respects_ring_limits() -> None:
    targets = select_candidate_targets(
        build_ring_graph(),
        *SANTIAGO_CENTER,
        ring_min_m=10_500,
        ring_max_m=11_500,
    )

    assert len(targets) == 8
    assert all(target.ring_distance_km == pytest.approx(11.0) for target in targets)


def test_select_candidates_rejects_bad_ring() -> None:
    with pytest.raises(ValueError):
        select_candidate_targets(
            build_ring_graph(), *SANTIAGO_CENTER, ring_min_m=12_000, ring_max_m=8_000
        )


def test_nearest_graph_node() -> None:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    add_node(G, 1, *SANTIAGO_CENTER)
    lat, lon = offset(*SANTIAGO_CENTER, 0, 10_000)
    add_node(G, 2, lat, lon)

    node, distance = nearest_graph_node(G, *SANTIAGO_CENTER)

    assert node == 1
    assert distance < 1.0


def test_empty_graph_has_no_nearest_node() -> None:
    with pytest.raises(OriginOutsideCoverageError):
        nearest_graph_node(nx.MultiDiGraph(), *SANTIAGO_CENTER)


# --- Rutas candidatas -----------------------------------------------------


def test_route_candidates_returns_two_per_sector() -> None:
    routes = route_candidates(
        build_ring_graph(), *SANTIAGO_CENTER, avg_speed_kmh=20
    )

    assert len(routes) == 16
    assert [route.direction for route in routes[:2]] == ["N", "N"]
    assert [route.direction for route in routes[-2:]] == ["NW", "NW"]
    assert all(route.time_min == pytest.approx(route.distance_km / 20 * 60, abs=0.1) for route in routes)
    assert all(route.geometry[0] == pytest.approx((SANTIAGO_CENTER[1], SANTIAGO_CENTER[0])) for route in routes)


def test_origin_too_far_from_graph() -> None:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    lat, lon = offset(*SANTIAGO_CENTER, 90, MAX_ORIGIN_SNAP_M * 3)
    add_node(G, 1, lat, lon)

    with pytest.raises(OriginOutsideCoverageError):
        route_candidates(G, *SANTIAGO_CENTER)


def test_no_candidates_inside_ring() -> None:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    add_node(G, 1, *SANTIAGO_CENTER)
    lat, lon = offset(*SANTIAGO_CENTER, 90, 1_000)
    add_node(G, 2, lat, lon)
    add_road(G, 1, 2, 1_000)

    with pytest.raises(NoCandidatesError):
        route_candidates(G, *SANTIAGO_CENTER)


def test_unreachable_candidates_raise() -> None:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    add_node(G, 1, *SANTIAGO_CENTER)
    add_node(G, 2, *offset(*SANTIAGO_CENTER, 90, 10_000))
    add_road(G, 2, 1, 10_000)  # solo en sentido contrario

    with pytest.raises(NoCandidatesError):
        route_candidates(G, *SANTIAGO_CENTER)


def test_low_aversion_takes_short_but_stressful_route() -> None:
    route = route_candidates(
        build_two_path_graph(), *SANTIAGO_CENTER, traffic_aversion=0
    )[0]

    assert route.distance_km == pytest.approx(10.0)
    assert route.avg_road_stress == pytest.approx(90.0)
    assert route.weighted_cost == pytest.approx(10_000)


def test_high_aversion_takes_long_but_quiet_route() -> None:
    route = route_candidates(
        build_two_path_graph(), *SANTIAGO_CENTER, traffic_aversion=1
    )[0]

    assert route.distance_km == pytest.approx(12.0)
    assert route.avg_road_stress == pytest.approx(10.0)
    assert route.weighted_cost == pytest.approx(15_600)


def test_parallel_edges_pick_the_cheaper_one() -> None:
    def graph() -> nx.MultiDiGraph:
        G = nx.MultiDiGraph()
        G.graph["crs"] = "epsg:4326"
        G.graph["cycle_escape_scored"] = True
        add_node(G, 1, *SANTIAGO_CENTER)
        add_node(G, 2, *offset(*SANTIAGO_CENTER, 90, 10_000))
        add_road(G, 1, 2, 10_000, road_stress=0, key=0)
        add_road(G, 1, 2, 5_000, road_stress=100, key=1)
        return G

    direct = route_candidates(graph(), *SANTIAGO_CENTER, traffic_aversion=0)[0]
    quiet = route_candidates(graph(), *SANTIAGO_CENTER, traffic_aversion=1)[0]

    assert direct.edges[0].key == 1
    assert direct.distance_km == pytest.approx(5.0)
    assert quiet.edges[0].key == 0
    assert quiet.distance_km == pytest.approx(10.0)


def test_edge_geometry_is_oriented_u_to_v() -> None:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.graph["cycle_escape_scored"] = True

    origin_lat, origin_lon = SANTIAGO_CENTER
    target_lat, target_lon = offset(*SANTIAGO_CENTER, 90, 10_000)
    add_node(G, 1, origin_lat, origin_lon)
    add_node(G, 2, target_lat, target_lon)

    # Geometría guardada al revés y con un punto intermedio.
    reversed_geometry = LineString(
        [
            (target_lon, target_lat),
            (origin_lon + (target_lon - origin_lon) / 2, origin_lat),
            (origin_lon, origin_lat),
        ]
    )
    add_road(
        G,
        1,
        2,
        10_000,
        road_stress=0,
        geometry=reversed_geometry,
    )

    route = route_candidates(G, *SANTIAGO_CENTER, traffic_aversion=0)[0]

    assert route.geometry[0] == pytest.approx((origin_lon, origin_lat))
    assert route.geometry[-1] == pytest.approx((target_lon, target_lat))
    assert len(route.geometry) == 3


def test_no_duplicate_points_between_edges() -> None:
    route = route_candidates(
        build_two_path_graph(), *SANTIAGO_CENTER, traffic_aversion=0
    )[0]

    assert all(
        first != second for first, second in zip(route.geometry, route.geometry[1:])
    )
    assert len(route.geometry) == len(route.edges) + 1


def test_route_candidates_rejects_bad_speed() -> None:
    with pytest.raises(ValueError):
        route_candidates(
            build_ring_graph(), *SANTIAGO_CENTER, avg_speed_kmh=0
        )


# --- Integración con el grafo real ----------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not cache_path().exists(),
    reason="requiere el grafo real cacheado en tmp/osm",
)
def test_real_santiago_routes() -> None:
    graph = get_graph()
    routes = route_candidates(
        graph, *SANTIAGO_CENTER, traffic_aversion=0.6
    )

    assert len(routes) >= 8
    assert len({route.direction for route in routes}) >= 6
    assert all(route.distance_km > 0 for route in routes)
    assert all(route.time_min > 0 for route in routes)
    assert all(0 <= route.avg_road_stress <= 100 for route in routes)
    assert all(route.geometry for route in routes)

    origin_lon, origin_lat = SANTIAGO_CENTER[1], SANTIAGO_CENTER[0]
    assert all(
        abs(route.geometry[0][0] - origin_lon) < 0.05
        and abs(route.geometry[0][1] - origin_lat) < 0.05
        for route in routes
    )
