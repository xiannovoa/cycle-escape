"""Tests del Road Stress base OSM, QuietScore y mezcla con tráfico medido."""

from __future__ import annotations

import logging
import math

import networkx as nx
import pytest

from app.scoring import (
    measured_traffic_stress,
    osm_road_stress,
    parse_lanes,
    parse_maxspeed,
    parse_surface,
    quiet_from_stress,
    resolve_heavy_pct,
    resolve_lanes,
    resolve_maxspeed,
    score_edge,
    score_graph_edges,
)


def make_edge(**overrides) -> dict:
    """Arista de referencia: calle residencial urbana, 30 km/h, un carril."""
    attrs = {
        "highway": "residential",
        "maxspeed": "30",
        "lanes": "1",
        "surface": "asphalt",
    }
    attrs.update(overrides)
    return attrs


# --- Parseo de atributos OSM ----------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("50", 50.0),
        ("50 km/h", 50.0),
        (["30"], 30.0),
        ("17,5", 17.5),
        ("walk", 7.0),
        ("none", 130.0),
        ("30 mph", 30 * 1.60934),
    ],
)
def test_parse_maxspeed(raw, expected: float) -> None:
    assert parse_maxspeed({"maxspeed": raw}) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "signals", "variable", "", []])
def test_parse_maxspeed_unparseable(raw) -> None:
    assert parse_maxspeed({"maxspeed": raw}) is None


def test_parse_maxspeed_direction_variants() -> None:
    assert parse_maxspeed({"maxspeed:forward": "70"}) == 70.0
    assert parse_maxspeed({"maxspeed:backward": "50 km/h"}) == 50.0


@pytest.mark.parametrize(
    ("highway", "expected"),
    [("trunk", 90.0), ("secondary", 70.0), ("residential", 30.0), ("raro", 50.0)],
)
def test_resolve_maxspeed_uses_osm_defaults(highway: str, expected: float) -> None:
    assert resolve_maxspeed({"highway": highway}) == expected


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        ({"lanes": "2"}, 2),
        ({"lanes": ["3"]}, 3),
        ({"lanes": "0", "lanes:forward": "2", "lanes:backward": "1"}, 3),
        ({"lanes": "0"}, None),
        ({}, None),
    ],
)
def test_parse_lanes(attrs: dict, expected: int | None) -> None:
    assert parse_lanes(attrs) == expected


def test_resolve_lanes_uses_osm_defaults() -> None:
    assert resolve_lanes({"highway": "secondary"}) == 2
    assert resolve_lanes({"highway": "residential"}) == 1


def test_parse_surface_normalizes() -> None:
    assert parse_surface({"surface": "Asphalt"}) == "asphalt"
    assert parse_surface({"surface": ["gravel"]}) == "gravel"
    assert parse_surface({}) is None


def test_resolve_heavy_pct() -> None:
    assert resolve_heavy_pct({"heavy_pct": 8.5}) == 8.5
    assert resolve_heavy_pct({"heavy_pct": ["4.2"]}) == 4.2
    assert resolve_heavy_pct({"heavy_pct": -1, "highway": "residential"}) == 1.0
    assert resolve_heavy_pct({"highway": "trunk"}) == 12.0
    assert resolve_heavy_pct({"highway": "residential"}) == 1.0


# --- Fórmula base ---------------------------------------------------------


def test_reference_residential_street() -> None:
    stress = osm_road_stress(make_edge())

    assert stress == pytest.approx(12.0)
    assert quiet_from_stress(stress) == pytest.approx(88.0)


def test_speed_increases_stress() -> None:
    stresses = [
        osm_road_stress(make_edge(maxspeed=str(speed)))
        for speed in (30, 50, 70, 90)
    ]

    assert stresses == sorted(stresses)
    assert len(set(stresses)) == len(stresses)


def test_more_lanes_increase_stress() -> None:
    stresses = [
        osm_road_stress(make_edge(lanes=str(lanes))) for lanes in (1, 2, 3, 4)
    ]

    assert stresses == sorted(stresses)
    assert len(set(stresses)) == len(stresses)


def test_worse_surfaces_increase_stress() -> None:
    stresses = [
        osm_road_stress(make_edge(surface=surface))
        for surface in ("asphalt", "paving_stones", "gravel", "unpaved")
    ]

    assert stresses == sorted(stresses)
    assert len(set(stresses)) == len(stresses)


def test_unknown_surface_is_not_free_of_stress() -> None:
    unknown = osm_road_stress(make_edge(surface=None))
    asphalt = osm_road_stress(make_edge(surface="asphalt"))

    assert unknown > asphalt


def test_highway_class_ordering() -> None:
    classes = (
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "residential",
        "living_street",
    )
    stresses = [
        osm_road_stress(
            make_edge(highway=highway, maxspeed="50", lanes="2", heavy_pct=5)
        )
        for highway in classes
    ]

    assert stresses == sorted(stresses, reverse=True)


def test_bike_infrastructure_reduces_stress() -> None:
    base = osm_road_stress(make_edge())
    lane = osm_road_stress(make_edge(**{"cycleway:right": "lane"}))
    track = osm_road_stress(make_edge(**{"cycleway:right": "track"}))
    designated = osm_road_stress(make_edge(bicycle="designated"))
    shoulder = osm_road_stress(make_edge(shoulder="yes"))

    assert lane < base
    assert track < lane
    assert designated < base
    assert shoulder < base


def test_bike_bonus_is_capped() -> None:
    stress = osm_road_stress(
        make_edge(
            **{
                "cycleway:right": "track",
                "bicycle": "designated",
                "shoulder": "yes",
            }
        )
    )

    assert stress == pytest.approx(0.0)


def test_cycleway_highway_is_very_quiet() -> None:
    assert osm_road_stress(make_edge(highway="cycleway")) == pytest.approx(0.0)


# --- Tráfico medido -------------------------------------------------------


def measured_edge(**overrides) -> dict:
    attrs = make_edge(
        highway="trunk",
        maxspeed="90",
        lanes="2",
        surface="asphalt",
        imd=23000,
        heavy_pct=9.8,
        traffic_source="mitma",
        traffic_year=2022,
        traffic_confidence="high",
    )
    attrs.update(overrides)
    return attrs


def test_measured_traffic_raises_stress_on_busy_road() -> None:
    attrs = measured_edge()
    base = osm_road_stress(attrs)
    result = score_edge(attrs)

    assert base == pytest.approx(61.2)
    assert result.road_stress == pytest.approx(70.4)
    assert result.quiet_score == pytest.approx(29.6)
    assert result.road_stress > base
    assert result.traffic_source == "mitma"
    assert result.traffic_confidence == "high"


def test_measured_quiet_road_lowers_stress() -> None:
    attrs = measured_edge(
        imd=300,
        heavy_pct=1.0,
        traffic_source="xunta",
        traffic_year=2025,
        traffic_confidence="high",
    )

    assert score_edge(attrs).road_stress < osm_road_stress(attrs)


def test_imd_monotonic() -> None:
    stresses = [
        score_edge(measured_edge(imd=imd)).road_stress
        for imd in (500, 5_000, 25_000)
    ]

    assert stresses == sorted(stresses)
    assert len(set(stresses)) == len(stresses)


def test_measured_heavy_traffic_monotonic() -> None:
    stresses = [
        score_edge(measured_edge(heavy_pct=heavy)).road_stress
        for heavy in (1, 5, 10)
    ]

    assert stresses == sorted(stresses)


def test_missing_heavy_pct_uses_prior_not_zero() -> None:
    attrs = measured_edge()
    del attrs["heavy_pct"]

    result = score_edge(attrs)

    assert result.components["measured"] == pytest.approx(82.3)
    assert result.components["measured"] > measured_traffic_stress(23000, 0)


def test_imd_without_measured_source_is_ignored() -> None:
    attrs = make_edge(imd=23000)

    result = score_edge(attrs)

    assert result.road_stress == osm_road_stress(attrs)
    assert result.traffic_source == "osm_estimate"
    assert result.components["measured"] == 0.0


def test_imd_marked_as_osm_estimate_is_ignored() -> None:
    attrs = make_edge(imd=23000, traffic_source="osm_estimate")

    result = score_edge(attrs)

    assert result.traffic_source == "osm_estimate"
    assert result.components["measured"] == 0.0


def test_score_graph_warns_once_about_orphan_imd(caplog) -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, **make_edge(imd=23000))
    graph.add_edge(2, 3, **make_edge(imd=12000))

    with caplog.at_level(logging.WARNING):
        score_graph_edges(graph)

    warnings = [r for r in caplog.records if "se ignoró el aforo" in r.message]
    assert len(warnings) == 1
    assert all(
        attrs["traffic_source"] == "osm_estimate"
        for _, _, attrs in graph.edges(data=True)
    )


# --- Procedencia y confianza ---------------------------------------------


def test_measured_confidence_falls_back_to_medium() -> None:
    attrs = measured_edge()
    del attrs["traffic_confidence"]

    assert score_edge(attrs).traffic_confidence == "medium"


def test_unmeasured_rich_osm_gets_medium_confidence() -> None:
    assert score_edge(make_edge()).traffic_confidence == "medium"


def test_unmeasured_sparse_osm_gets_low_confidence() -> None:
    assert score_edge({"highway": "residential"}).traffic_confidence == "low"


def test_score_is_bounded_and_consistent() -> None:
    cases = [
        {},
        make_edge(highway=["secondary"], maxspeed="bad", lanes="x"),
        make_edge(highway="trunk", maxspeed="100 km/h", lanes="4", heavy_pct=50),
        make_edge(highway="cycleway", bicycle="designated"),
        measured_edge(imd=200_000, heavy_pct=40),
    ]

    for attrs in cases:
        result = score_edge(attrs)
        assert 0 <= result.road_stress <= 100
        assert 0 <= result.quiet_score <= 100
        assert not math.isnan(result.road_stress)
        assert result.quiet_score == pytest.approx(100 - result.road_stress, abs=0.1)
        assert result.traffic_source in {"xunta", "mitma", "osm_estimate"}
        assert result.traffic_confidence in {"high", "medium", "low"}


# --- Aplicación al grafo --------------------------------------------------


def test_score_graph_edges_annotates_without_inventing_traffic() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, **make_edge())
    graph.add_edge(
        2,
        3,
        **measured_edge(
            highway="trunk",
            maxspeed="90",
            lanes="2",
            surface="asphalt",
        ),
    )

    returned = score_graph_edges(graph)

    assert returned is graph

    first = graph.edges[1, 2, 0]
    assert first["road_stress"] == pytest.approx(12.0)
    assert first["quiet_score"] == pytest.approx(88.0)
    assert first["traffic_source"] == "osm_estimate"
    assert first["traffic_confidence"] == "medium"
    assert "imd" not in first
    assert "heavy_pct" not in first

    second = graph.edges[2, 3, 0]
    assert second["traffic_source"] == "mitma"
    assert second["traffic_confidence"] == "high"
    assert second["imd"] == 23000
    assert second["road_stress"] > first["road_stress"]
