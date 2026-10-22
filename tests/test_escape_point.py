"""Tests de la detección del Escape Point y del ranking de corredores."""

from __future__ import annotations

import pytest
import networkx as nx

from app.graph_loader import SANTIAGO_CENTER, cache_path, get_graph
from app.escape_point import (
    DEFAULT_THRESHOLDS,
    EscapeThresholds,
    NoSustainedQuietError,
    NodeDensityIndex,
    detect_escape_point,
    rank_escape_routes,
)
from app.routing import (
    CandidateRoute,
    NoCandidatesError,
    PathEdge,
    route_candidates,
)


# --- Construcción de rutas sintéticas -------------------------------------


def make_edge(
    index: int,
    length_m: float,
    stress: float,
    name: str | None = None,
    ref: str | None = None,
) -> PathEdge:
    lon0 = -8.55 + index * 0.002
    lon1 = lon0 + 0.002
    attrs: dict = {"length": length_m, "road_stress": stress}
    if name is not None:
        attrs["name"] = name
    if ref is not None:
        attrs["ref"] = ref
    return PathEdge(
        u=index,
        v=index + 1,
        key=0,
        length_m=float(length_m),
        road_stress=float(stress),
        coordinates=((lon0, 42.88), (lon1, 42.88)),
        attrs=attrs,
    )


def make_route(
    specs: list[tuple[float, float]],
    *,
    direction: str = "E",
    avg_speed_kmh: float = 20.0,
    names: list[str | None] | None = None,
) -> CandidateRoute:
    edges: list[PathEdge] = []
    geometry: list[tuple[float, float]] = []

    for index, (length, stress) in enumerate(specs):
        name = names[index] if names else None
        edge = make_edge(index, length, stress, name=name)
        edges.append(edge)
        for coordinate in edge.coordinates:
            if not geometry or geometry[-1] != coordinate:
                geometry.append(coordinate)

    total_length = sum(length for length, _ in specs)
    total_km = total_length / 1000.0
    avg_stress = (
        sum(length * stress for length, stress in specs) / total_length
        if total_length > 0
        else 0.0
    )
    time_min = total_km / avg_speed_kmh * 60.0

    return CandidateRoute(
        direction=direction,  # type: ignore[arg-type]
        target_node=999,
        target_lat=42.9,
        target_lon=-8.5,
        ring_distance_km=10.0,
        distance_km=round(total_km, 3),
        time_min=round(time_min, 1),
        avg_speed_kmh=avg_speed_kmh,
        weighted_cost=0.0,
        avg_road_stress=round(avg_stress, 1),
        geometry=tuple(geometry),
        edges=tuple(edges),
    )


def busy_then_quiet() -> CandidateRoute:
    return make_route([(1000, 80)] * 4 + [(1000, 20)] * 6)


# --- Detección ------------------------------------------------------------


def test_detects_first_sustained_quiet_point() -> None:
    route = busy_then_quiet()
    point = detect_escape_point(route)

    assert point.valid is True
    assert point.edge_index == 4
    assert point.window.covered_km == pytest.approx(5.0)
    assert point.window.mean_quiet_score == pytest.approx(80.0)
    assert point.window.quiet_share == pytest.approx(1.0)
    assert point.window.max_stress == pytest.approx(20.0)
    assert (point.lon, point.lat) == pytest.approx(
        route.edges[4].coordinates[0]
    )
    assert point.warnings == ()


def test_does_not_stop_at_first_temporary_calm() -> None:
    # Dos tramos tranquilos seguidos de tráfico: no son una ventana sostenida.
    route = make_route(
        [(1000, 80)] * 2
        + [(1000, 20)] * 2
        + [(1000, 90)]
        + [(1000, 20)] * 5
    )

    point = detect_escape_point(route)

    assert point.valid is True
    assert point.edge_index == 5


def test_all_quiet_route_escapes_at_origin() -> None:
    point = detect_escape_point(make_route([(1000, 20)] * 5))

    assert point.valid is True
    assert point.edge_index == 0


def test_quiet_share_is_required() -> None:
    route = make_route(
        [(1000, 80)] * 2
        + [(1000, 50), (1000, 20), (1000, 20)]
        + [(1000, 20)] * 4
    )

    point = detect_escape_point(
        route, EscapeThresholds(window_km=3.0)
    )

    assert point.edge_index == 3
    assert point.valid is True


def test_mean_quiet_threshold() -> None:
    route = make_route([(1000, 80)] * 2 + [(1000, 30)] * 6)

    default_point = detect_escape_point(route)
    strict_point = detect_escape_point(
        route, EscapeThresholds(min_mean_quiet=70.1)
    )

    assert default_point.valid is True
    assert default_point.edge_index == 2
    assert strict_point.valid is False


def test_extreme_stress_vetoes_the_window() -> None:
    route = make_route(
        [(1000, 80)] * 2
        + [(1000, 20)] * 2
        + [(1000, 90)]
        + [(1000, 20)] * 5
    )

    point = detect_escape_point(route)

    assert point.edge_index == 5


def test_fallback_marks_point_as_estimated() -> None:
    point = detect_escape_point(make_route([(1000, 80)] * 10))

    assert point.valid is False
    assert point.edge_index == 0
    assert point.warnings
    assert "estimado" in point.warnings[0].lower()


def test_strict_mode_raises_without_valid_window() -> None:
    with pytest.raises(NoSustainedQuietError):
        detect_escape_point(
            make_route([(1000, 80)] * 10), allow_fallback=False
        )


def test_short_route_fallback_explains_why() -> None:
    point = detect_escape_point(make_route([(500, 80)] * 2))

    assert point.valid is False
    assert any("más corta" in warning for warning in point.warnings)


def test_escape_point_name_falls_back_to_ref() -> None:
    named = make_route([(1000, 20)] * 5, names=["Rúa de Roxos"] * 5)
    referenced = CandidateRoute(
        **{
            **named.__dict__,
            "edges": tuple(
                PathEdge(
                    u=edge.u,
                    v=edge.v,
                    key=edge.key,
                    length_m=edge.length_m,
                    road_stress=edge.road_stress,
                    coordinates=edge.coordinates,
                    attrs={"length": edge.length_m, "road_stress": 20, "ref": "AC-543"},
                )
                for edge in named.edges
            ),
        }
    )

    assert detect_escape_point(named).name == "Rúa de Roxos"
    assert detect_escape_point(referenced).name == "AC-543"


# --- Densidad urbana ------------------------------------------------------


class StubDensity:
    """Densidad falsa por longitud, para probar el veto sin grafo real."""

    def __init__(self, counts: dict[float, int]) -> None:
        self.counts = counts

    def count_within(self, lon: float, lat: float, radius_m: float = 500.0) -> int:
        return self.counts.get(round(lon, 6), 0)


def test_density_veto_skips_dense_points() -> None:
    route = make_route([(1000, 20)] * 5)
    counts = {
        round(-8.55, 6): 120,
        round(-8.548, 6): 90,
        round(-8.546, 6): 20,
    }
    thresholds = EscapeThresholds(window_km=3.0, max_urban_nodes=60)

    point = detect_escape_point(
        route,
        thresholds,
        density_index=StubDensity(counts),
    )

    assert point.edge_index == 2
    assert point.valid is True


def test_density_can_be_disabled() -> None:
    route = make_route([(1000, 20)] * 5)
    counts = {round(-8.55 + i * 0.002, 6): 1_000 for i in range(5)}
    thresholds = EscapeThresholds(max_urban_nodes=None)

    point = detect_escape_point(
        route, thresholds, density_index=StubDensity(counts)
    )

    assert point.edge_index == 0


def test_node_density_index_counts_nearby_nodes() -> None:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"

    for node, lon_offset, lat_offset in (
        (1, 0.0, 0.0),
        (2, 0.0005, 0.0),
        (3, 0.001, 0.0),
        (4, 0.05, 0.0),  # ~5 km
    ):
        graph.add_node(
            node,
            x=SANTIAGO_CENTER[1] + lon_offset,
            y=SANTIAGO_CENTER[0] + lat_offset,
        )

    index = NodeDensityIndex(graph)

    assert index.count_within(*SANTIAGO_CENTER[::-1], radius_m=500) == 3
    assert index.count_within(SANTIAGO_CENTER[1] + 0.05, SANTIAGO_CENTER[0], radius_m=500) == 1


def test_node_density_index_rejects_empty_graph() -> None:
    with pytest.raises(ValueError):
        NodeDensityIndex(nx.MultiDiGraph())


# --- Métricas y ranking ---------------------------------------------------


def test_escape_metrics_and_post_escape_quiet() -> None:
    result = rank_escape_routes([busy_then_quiet()], max_routes=1)[0]

    assert result.distance_to_escape_km == pytest.approx(4.0)
    assert result.escape_time_min == pytest.approx(12.0)
    assert result.quiet_score == pytest.approx(80.0)
    assert result.post_escape_stress == pytest.approx(20.0)
    assert result.avg_road_stress == pytest.approx(44.0)
    assert result.rank == 1
    assert result.is_recommended is True


def test_route_id_uses_direction_and_place_name() -> None:
    route = make_route(
        [(1000, 20)] * 5, direction="W", names=["Rúa de Roxos"] * 5
    )

    result = rank_escape_routes([route])[0]

    assert result.id == "oeste-rua-de-roxos"


def test_route_id_without_name_is_direction_only() -> None:
    result = rank_escape_routes([make_route([(1000, 20)] * 5, direction="NW")])[0]

    assert result.id == "noroeste"


def fast_route(direction: str = "E") -> CandidateRoute:
    """Escapa pronto, pero la red posterior empeora."""
    return make_route(
        [(1000, 80)] + [(1000, 20)] * 5 + [(1000, 80)] * 7,
        direction=direction,
    )


def calm_route(direction: str = "W") -> CandidateRoute:
    """Tarda más en escapar, pero después la red es muy tranquila."""
    return make_route(
        [(1000, 80)] * 8 + [(1000, 10)] * 6,
        direction=direction,
    )


def test_direct_preference_prefers_early_escape() -> None:
    routes = rank_escape_routes(
        [fast_route(), calm_route()], route_preference="direct"
    )

    assert routes[0].id == "este"
    assert routes[0].is_recommended is True


def test_quiet_preference_prefers_calm_network() -> None:
    routes = rank_escape_routes(
        [fast_route(), calm_route()], route_preference="quiet"
    )

    assert routes[0].id == "oeste"


def test_lambda_zero_prefers_escaping_early() -> None:
    routes = rank_escape_routes(
        [fast_route(), calm_route()], traffic_lambda=0
    )

    assert routes[0].id == "este"


def test_lambda_one_prefers_calm_network() -> None:
    routes = rank_escape_routes(
        [fast_route(), calm_route()], traffic_lambda=1
    )

    assert routes[0].id == "oeste"


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_invalid_traffic_lambda(value: float) -> None:
    with pytest.raises(ValueError):
        rank_escape_routes([busy_then_quiet()], traffic_lambda=value)


def test_ranking_keeps_one_route_per_direction() -> None:
    routes = rank_escape_routes(
        [fast_route("E"), calm_route("E"), calm_route("W")]
    )

    assert len(routes) == 2
    assert [route.direction for route in routes].count("E") == 1
    assert routes[0].id == "este"
    assert sum(route.is_recommended for route in routes) == 1


def test_ranking_limits_and_flags() -> None:
    candidates = [
        make_route([(1000, 10)] * 5, direction=direction)
        for direction in ("N", "E", "S", "W")
    ]

    routes = rank_escape_routes(candidates, max_routes=2)

    assert len(routes) == 2
    assert [route.rank for route in routes] == [1, 2]
    assert sum(route.is_recommended for route in routes) == 1
    assert len({route.id for route in routes}) == 2


def test_valid_escape_always_beats_fallback() -> None:
    fallback = make_route([(1000, 80)] * 10, direction="NE")
    valid = make_route([(1000, 80)] * 4 + [(1000, 20)] * 6, direction="W")

    routes = rank_escape_routes([fallback, valid], max_routes=2)

    assert routes[0].escape_point.valid is True
    assert routes[0].direction == "W"
    assert routes[1].escape_point.valid is False

    only_one = rank_escape_routes([fallback, valid], max_routes=1)
    assert len(only_one) == 1
    assert only_one[0].escape_point.valid is True


def test_empty_candidates_raise() -> None:
    with pytest.raises(NoCandidatesError):
        rank_escape_routes([])


def test_invalid_preference_raises() -> None:
    with pytest.raises(ValueError):
        rank_escape_routes([busy_then_quiet()], route_preference="fast")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_km": 0},
        {"min_mean_quiet": 101},
        {"min_quiet_share": 1.5},
        {"quiet_stress_max": 80, "extreme_stress": 70},
        {"max_urban_nodes": -1},
        {"urban_radius_m": 0},
    ],
)
def test_invalid_thresholds(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        EscapeThresholds(**kwargs)


def test_default_thresholds_are_the_documented_ones() -> None:
    assert DEFAULT_THRESHOLDS.window_km == 5.0
    assert DEFAULT_THRESHOLDS.min_mean_quiet == 70.0
    assert DEFAULT_THRESHOLDS.min_quiet_share == 0.8
    assert DEFAULT_THRESHOLDS.extreme_stress == 75.0
    assert DEFAULT_THRESHOLDS.urban_radius_m == 1000.0
    assert DEFAULT_THRESHOLDS.max_urban_nodes == 200


# --- Integración con Santiago ---------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not cache_path().exists(),
    reason="requiere el grafo real cacheado en tmp/osm",
)
def test_real_santiago_escape_routes() -> None:
    graph = get_graph()
    candidates = route_candidates(
        graph, *SANTIAGO_CENTER, traffic_aversion=0.6
    )
    routes = rank_escape_routes(candidates, max_routes=5, graph=graph)
    density = NodeDensityIndex(graph)

    assert 1 <= len(routes) <= 5
    assert [route.rank for route in routes] == list(range(1, len(routes) + 1))
    assert sum(route.is_recommended for route in routes) == 1
    assert len({route.id for route in routes}) == len(routes)
    assert any(route.escape_point.valid for route in routes)

    for route in routes:
        assert route.distance_to_escape_km <= route.distance_km + 0.01
        assert route.escape_time_min <= route.time_min + 0.1
        assert 0 <= route.quiet_score <= 100
        assert 0 <= route.avg_road_stress <= 100
        assert route.escape_point.edge_index < len(route.edges)

        edge = route.edges[route.escape_point.edge_index]
        assert route.escape_point.lon == pytest.approx(edge.coordinates[0][0])
        assert route.escape_point.lat == pytest.approx(edge.coordinates[0][1])

        if route.escape_point.valid:
            assert (
                density.count_within(
                    route.escape_point.lon,
                    route.escape_point.lat,
                    DEFAULT_THRESHOLDS.urban_radius_m,
                )
                <= DEFAULT_THRESHOLDS.max_urban_nodes
            )
