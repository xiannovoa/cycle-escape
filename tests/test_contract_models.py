"""Validación del contrato de API (v0.1) contra los modelos del backend.

El JSON de `fixtures/contract_example_response.json` es el ejemplo publicado en
`docs/api-contract.md`. Sus geometrías y valores son ficticios: sirve para
comprobar la forma del contrato, no como dato real de tráfico.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import (
    DIRECTIONS,
    SCHEMA_VERSION,
    ErrorResponse,
    EscapeRoutesRequest,
    EscapeRoutesResponse,
    HealthResponse,
    LineString,
    Segment,
    TrafficSummary,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_example_response() -> dict:
    raw = (FIXTURES / "contract_example_response.json").read_text(encoding="utf-8")
    return json.loads(raw)


def make_segment(**overrides: object) -> Segment:
    data: dict = {
        "geometry": {
            "type": "LineString",
            "coordinates": [[-8.552, 42.876], [-8.564, 42.874]],
        },
        "road_name": "AC-543",
        "highway": "secondary",
        "surface": "asphalt",
        "road_stress": 48,
        "imd": None,
        "heavy_pct": None,
        "traffic_source": "osm_estimate",
        "traffic_year": None,
        "traffic_confidence": "low",
    }
    data.update(overrides)
    return Segment.model_validate(data)


# --- Ejemplo completo ------------------------------------------------------


def test_example_response_matches_contract() -> None:
    response = EscapeRoutesResponse.model_validate(load_example_response())

    assert response.schema_version == SCHEMA_VERSION
    assert response.recommended_route_id == "oeste-roxos"
    assert response.routes[0].id == response.recommended_route_id
    assert sum(route.is_recommended for route in response.routes) == 1
    assert {route.direction for route in response.routes} <= set(DIRECTIONS)


def test_example_response_round_trips_unchanged() -> None:
    example = load_example_response()
    response = EscapeRoutesResponse.model_validate(example)

    assert json.loads(response.model_dump_json()) == example


def test_geometry_keeps_lon_lat_order() -> None:
    response = EscapeRoutesResponse.model_validate(load_example_response())
    first = response.routes[0].geometry.coordinates[0]

    assert first == (-8.5448, 42.8782)


def test_generated_at_is_serialized_as_utc() -> None:
    example = load_example_response()
    example["generated_at"] = "2026-10-22T10:15:00+02:00"

    response = EscapeRoutesResponse.model_validate(example)

    assert json.loads(response.model_dump_json())["generated_at"] == (
        "2026-10-22T08:15:00Z"
    )


# --- Petición --------------------------------------------------------------


def test_request_defaults() -> None:
    request = EscapeRoutesRequest.model_validate(
        {"origin": {"lat": 42.8782, "lon": -8.5448}}
    )

    assert request.avg_speed_kmh == 22
    assert request.traffic_aversion == 0.5
    assert request.traffic_lambda is None
    assert request.surface_preference == "asphalt"
    assert request.route_preference == "balanced"
    assert request.max_candidates == 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("avg_speed_kmh", 9),
        ("avg_speed_kmh", 41),
        ("traffic_aversion", -0.1),
        ("traffic_aversion", 1.1),
        ("traffic_lambda", -0.1),
        ("traffic_lambda", 1.1),
        ("max_candidates", 0),
        ("max_candidates", 8),
        ("surface_preference", "gravel"),
        ("route_preference", "fast"),
    ],
)
def test_invalid_request_parameters(field: str, value: object) -> None:
    payload = {"origin": {"lat": 42.8782, "lon": -8.5448}, field: value}

    with pytest.raises(ValidationError):
        EscapeRoutesRequest.model_validate(payload)


def test_origin_is_required() -> None:
    with pytest.raises(ValidationError):
        EscapeRoutesRequest.model_validate({})


def test_request_accepts_speed_40_and_lambda_extremes() -> None:
    for value in (0, 1):
        request = EscapeRoutesRequest.model_validate(
            {
                "origin": {"lat": 42.8782, "lon": -8.5448},
                "avg_speed_kmh": 40,
                "traffic_lambda": value,
            }
        )
        assert request.avg_speed_kmh == 40
        assert request.traffic_lambda == value


# --- Geometría -------------------------------------------------------------


@pytest.mark.parametrize(
    "coordinates",
    [
        [[-8.5, 42.8]],
        [[-200.0, 42.8]],
        [[-8.5, 91.0]],
        [[-8.5, 42.8, 0.0]],
    ],
)
def test_invalid_linestring_coordinates(coordinates: list) -> None:
    with pytest.raises(ValidationError):
        LineString.model_validate({"type": "LineString", "coordinates": coordinates})


# --- Consistencia de tráfico ----------------------------------------------


def test_osm_estimate_cannot_carry_measurements() -> None:
    with pytest.raises(ValidationError):
        make_segment(imd=9200)
    with pytest.raises(ValidationError):
        make_segment(traffic_year=2025)


def test_measured_segment_without_imd_needs_low_confidence() -> None:
    with pytest.raises(ValidationError):
        make_segment(traffic_source="xunta", traffic_confidence="high")
    with pytest.raises(ValidationError):
        make_segment(traffic_source="mitma", traffic_confidence="medium")

    segment = make_segment(traffic_source="xunta", traffic_confidence="low")
    assert segment.traffic_source == "xunta"
    assert segment.imd is None


def test_measured_segment_with_imd_is_valid() -> None:
    segment = make_segment(
        traffic_source="xunta",
        traffic_year=2025,
        imd=9200,
        heavy_pct=5.1,
        traffic_confidence="high",
    )

    assert segment.imd == 9200
    assert segment.heavy_pct == 5.1


@pytest.mark.parametrize(
    "overrides",
    [
        {"heavy_pct": 101},
        {"heavy_pct": -1},
        {"imd": -1},
        {"road_stress": 101},
        {"road_stress": -1},
        {"traffic_source": "dgt"},
    ],
)
def test_segment_rejects_out_of_range_values(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        make_segment(**overrides)


def test_traffic_summary_requires_measured_source_when_share_is_positive() -> None:
    with pytest.raises(ValidationError):
        TrafficSummary(
            sources=["osm_estimate"],
            years=[],
            measured_share=0.4,
            confidence="medium",
        )

    summary = TrafficSummary(
        sources=["osm_estimate"],
        years=[],
        measured_share=0,
        confidence="low",
    )
    assert summary.measured_share == 0


def test_traffic_summary_needs_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        TrafficSummary(
            sources=[], years=[], measured_share=0, confidence="low"
        )


# --- Consistencia de la respuesta -----------------------------------------


def test_recommended_route_must_exist() -> None:
    example = copy.deepcopy(load_example_response())
    example["recommended_route_id"] = "no-existe"

    with pytest.raises(ValidationError):
        EscapeRoutesResponse.model_validate(example)


def test_only_one_route_can_be_recommended() -> None:
    example = copy.deepcopy(load_example_response())
    example["routes"][1]["is_recommended"] = True

    with pytest.raises(ValidationError):
        EscapeRoutesResponse.model_validate(example)


def test_route_ids_must_be_unique() -> None:
    example = copy.deepcopy(load_example_response())
    example["routes"][1]["id"] = example["routes"][0]["id"]

    with pytest.raises(ValidationError):
        EscapeRoutesResponse.model_validate(example)


def test_response_needs_at_least_one_route() -> None:
    example = copy.deepcopy(load_example_response())
    example["routes"] = []

    with pytest.raises(ValidationError):
        EscapeRoutesResponse.model_validate(example)


def test_scores_are_bounded() -> None:
    example = copy.deepcopy(load_example_response())
    example["routes"][0]["quiet_score"] = 101

    with pytest.raises(ValidationError):
        EscapeRoutesResponse.model_validate(example)


# --- Direcciones, salud y errores -----------------------------------------


def test_directions_cover_the_eight_sectors() -> None:
    assert DIRECTIONS == ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def test_unknown_direction_is_rejected() -> None:
    example = copy.deepcopy(load_example_response())
    example["routes"][0]["direction"] = "O"

    with pytest.raises(ValidationError):
        EscapeRoutesResponse.model_validate(example)


def test_health_response() -> None:
    health = HealthResponse.model_validate(
        {
            "status": "ok",
            "osm_graph_loaded": True,
            "traffic_layers": ["xunta", "mitma"],
        }
    )

    assert health.schema_version == SCHEMA_VERSION


def test_error_response_example() -> None:
    error = ErrorResponse.model_validate(
        {
            "error": {
                "code": "NO_ROUTES_FOUND",
                "message": "No se han encontrado corredores de escape para este origen.",
                "details": {},
            }
        }
    )

    assert error.error.code == "NO_ROUTES_FOUND"


def test_unknown_error_code_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorResponse.model_validate(
            {"error": {"code": "OOPS", "message": "x", "details": {}}}
        )
