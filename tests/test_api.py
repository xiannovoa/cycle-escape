"""Tests de la API: contrato, errores, CORS y recorrido completo."""

from __future__ import annotations

import math

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer

from app import main
from app.data_loader import SANTIAGO_CENTER, cache_path, get_graph
from app.main import create_app
from app.models import DIRECTIONS, EscapeRoutesResponse

ORIGIN = {"lat": SANTIAGO_CENTER[0], "lon": SANTIAGO_CENTER[1]}


# --- Grafo sintético ------------------------------------------------------


def _transformers(lat: float, lon: float) -> tuple[Transformer, Transformer]:
    zone = int((lon + 180.0) // 6.0) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return (
        Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True),
        Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True),
    )


def _offset(lat: float, lon: float, bearing: float, distance_m: float):
    forward, inverse = _transformers(lat, lon)
    x, y = forward.transform(lon, lat)
    radians = math.radians(bearing)
    x += distance_m * math.sin(radians)
    y += distance_m * math.cos(radians)
    lon2, lat2 = inverse.transform(x, y)
    return lat2, lon2


def build_api_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_node(1, x=SANTIAGO_CENTER[1], y=SANTIAGO_CENTER[0])

    node = 2
    for index, direction in enumerate(DIRECTIONS):
        for distance in (9_000.0, 11_000.0):
            lat, lon = _offset(*SANTIAGO_CENTER, index * 45.0, distance)
            graph.add_node(node, x=lon, y=lat)
            graph.add_edge(
                1,
                node,
                key=0,
                length=distance,
                highway="tertiary",
                maxspeed="30",
                lanes="1",
                surface="asphalt",
                name=f"Camino {direction}",
                ref=f"CP-{node}",
            )
            node += 1

    return graph


def make_client(graph: nx.MultiDiGraph | None = None, **kwargs) -> TestClient:
    app = create_app(graph=graph, load_graph=False, **kwargs)
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    with make_client(build_api_graph()) as test_client:
        yield test_client


# --- Salud ----------------------------------------------------------------


def test_health_ok_with_graph(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["osm_graph_loaded"] is True
    assert payload["traffic_layers"] == ["osm_estimate"]
    assert payload["schema_version"] == "0.1"


def test_health_degraded_without_graph() -> None:
    with make_client(None) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["osm_graph_loaded"] is False


# --- Respuesta principal --------------------------------------------------


def test_escape_routes_matches_contract(client: TestClient) -> None:
    response = client.post("/api/escape-routes", json={"origin": ORIGIN})

    assert response.status_code == 200
    payload = response.json()
    model = EscapeRoutesResponse.model_validate(payload)

    assert model.recommended_route_id == model.routes[0].id
    assert sum(route.is_recommended for route in model.routes) == 1
    assert len(model.routes) == 5

    route = model.routes[0]
    assert route.label.startswith("Norte vía Camino N")
    assert route.geometry.type == "LineString"
    assert route.geometry.coordinates[0] == pytest.approx(
        (ORIGIN["lon"], ORIGIN["lat"])
    )
    assert route.escape_point.lon == pytest.approx(ORIGIN["lon"])
    assert route.escape_point.lat == pytest.approx(ORIGIN["lat"])
    assert route.escape_point.name == "Camino N"

    assert route.segments
    segment = route.segments[0]
    assert segment.traffic_source == "osm_estimate"
    assert segment.imd is None
    assert segment.traffic_year is None
    assert segment.traffic_confidence == "medium"
    assert 0 <= segment.road_stress <= 100

    assert route.traffic_summary.sources == ["osm_estimate"]
    assert route.traffic_summary.measured_share == 0
    assert route.traffic_summary.confidence == "low"
    assert route.traffic_summary.years == []

    assert payload["warnings"]


def test_max_candidates_is_honored(client: TestClient) -> None:
    response = client.post(
        "/api/escape-routes",
        json={"origin": ORIGIN, "max_candidates": 2},
    )

    assert response.status_code == 200
    assert len(response.json()["routes"]) == 2


def test_explicit_preferences_are_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/escape-routes",
        json={
            "origin": ORIGIN,
            "avg_speed_kmh": 25,
            "traffic_aversion": 0.8,
            "route_preference": "quiet",
            "surface_preference": "mixed",
            "max_candidates": 3,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["routes"]) == 3


# --- Errores --------------------------------------------------------------


def test_invalid_origin_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/escape-routes",
        json={"origin": {"lat": 999, "lon": 0}},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ORIGIN"


def test_invalid_parameter_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/escape-routes",
        json={"origin": ORIGIN, "max_candidates": 9},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


def test_origin_outside_coverage_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/escape-routes",
        json={"origin": {"lat": 40.4168, "lon": -3.7038}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OUTSIDE_COVERAGE"


def test_missing_graph_returns_503() -> None:
    with make_client(None) as client:
        response = client.post("/api/escape-routes", json={"origin": ORIGIN})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATA_NOT_READY"


def test_unexpected_error_returns_stable_500(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(main, "route_candidates", boom)

    app = create_app(graph=build_api_graph(), load_graph=False)
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/api/escape-routes", json={"origin": ORIGIN}
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ROUTING_ERROR"


# --- CORS -----------------------------------------------------------------


def test_cors_preflight_allows_vite(client: TestClient) -> None:
    response = client.options(
        "/api/escape-routes",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:5173"
    )


# --- Integración con Santiago ---------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not cache_path().exists(),
    reason="requiere el grafo real cacheado en tmp/osm",
)
def test_real_santiago_api() -> None:
    graph = get_graph()
    with make_client(graph) as client:
        response = client.post("/api/escape-routes", json={"origin": ORIGIN})

    assert response.status_code == 200
    payload = response.json()
    model = EscapeRoutesResponse.model_validate(payload)

    assert 1 <= len(model.routes) <= 5
    assert sum(route.is_recommended for route in model.routes) == 1
    assert any(route.escape_time_min > 0 for route in model.routes)
    assert all(route.segments for route in model.routes)
    assert all(
        42.7 < route.escape_point.lat < 43.1
        and -8.8 < route.escape_point.lon < -8.3
        for route in model.routes
    )
    for route in model.routes:
        assert any(
            abs(lon - route.escape_point.lon) < 1e-6
            and abs(lat - route.escape_point.lat) < 1e-6
            for lon, lat in route.geometry.coordinates
        )
