"""Tests del cargador de grafo: filtrado ciclista, caché y diagnóstico."""

from __future__ import annotations

import json
import os

import networkx as nx
import osmnx as ox
import pytest

from app import data_loader
from app.data_loader import (
    CACHE_VERSION,
    SANTIAGO_CENTER,
    GraphUnavailableError,
    cache_path,
    filter_bike_unsuitable,
    get_graph,
    graph_summary,
    is_bike_suitable,
    keep_largest_component,
)


# --- Aptitud ciclista ------------------------------------------------------


@pytest.mark.parametrize(
    "attrs",
    [
        {"highway": "secondary"},
        {"highway": "trunk", "maxspeed": "90"},
        {"highway": "residential", "maxspeed": ["30"]},
        {"highway": "tertiary", "surface": "asphalt"},
        {"highway": "service", "bicycle": ["yes"]},
        {"highway": "primary", "access": "private", "bicycle": "yes"},
        {"highway": "secondary", "motorroad": "no"},
    ],
)
def test_bike_suitable_edges(attrs: dict) -> None:
    assert is_bike_suitable(attrs) is True


@pytest.mark.parametrize(
    "attrs",
    [
        {},
        {"highway": "motorway"},
        {"highway": "motorway_link", "bicycle": "yes"},
        {"highway": "busway"},
        {"highway": "raceway"},
        {"highway": "secondary", "bicycle": "no"},
        {"highway": "secondary", "access": "no"},
        {"highway": "secondary", "access": "private"},
        {"highway": "secondary", "vehicle": "no"},
        {"highway": "primary", "motorroad": "yes"},
        {"highway": "secondary", "access": "private", "bicycle": "no"},
    ],
)
def test_bike_unsuitable_edges(attrs: dict) -> None:
    assert is_bike_suitable(attrs) is False


# --- Filtrado y limpieza --------------------------------------------------


def build_mixed_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"

    G.add_edge(1, 2, key=0, highway="secondary", length=100.0)
    G.add_edge(2, 3, key=0, highway="motorway", length=500.0)
    G.add_edge(3, 4, key=0, highway="secondary", bicycle="no", length=200.0)
    G.add_edge(4, 5, key=0, highway="residential", access="private", length=50.0)
    G.add_edge(5, 6, key=0, highway="tertiary", length=300.0)
    G.add_edge(6, 1, key=0, highway="residential", length=400.0)
    return G


def test_filter_removes_unsuitable_edges_and_isolated_nodes() -> None:
    graph = filter_bike_unsuitable(build_mixed_graph())

    assert set(graph.nodes) == {1, 2, 5, 6}
    assert set(graph.edges) == {(1, 2, 0), (5, 6, 0), (6, 1, 0)}
    assert list(nx.isolates(graph)) == []


def test_filter_keeps_valid_graph_unchanged() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, highway="secondary", length=10.0)

    filter_bike_unsuitable(graph)

    assert set(graph.edges) == {(1, 2, 0)}


def test_keep_largest_component() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, highway="secondary", length=10.0)
    graph.add_edge(2, 3, highway="secondary", length=10.0)
    graph.add_edge(10, 11, highway="secondary", length=10.0)

    largest = keep_largest_component(graph)

    assert set(largest.nodes) == {1, 2, 3}


# --- Caché ----------------------------------------------------------------


def test_cache_path_is_deterministic(tmp_path) -> None:
    first = cache_path(SANTIAGO_CENTER, 12_000, "drive", tmp_path)
    second = cache_path(SANTIAGO_CENTER, 12_000, "drive", tmp_path)

    assert first == second
    assert first.name == f"graph_42.8782_-8.5448_r12000_drive_v{CACHE_VERSION}.graphml"


def test_cache_path_varies_with_area_and_network(tmp_path) -> None:
    base = cache_path(SANTIAGO_CENTER, 12_000, "drive", tmp_path)

    assert cache_path(SANTIAGO_CENTER, 8_000, "drive", tmp_path) != base
    assert cache_path(SANTIAGO_CENTER, 12_000, "drive_service", tmp_path) != base
    assert cache_path((42.88, -8.55), 12_000, "drive", tmp_path) != base


def test_get_graph_rejects_invalid_radius(tmp_path) -> None:
    with pytest.raises(ValueError):
        get_graph(radius_m=0, cache_dir=tmp_path)


def test_get_graph_uses_cache_without_network(tmp_path, monkeypatch) -> None:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_edge(1, 2, key=0, highway="secondary", length=120.0)
    path = cache_path(SANTIAGO_CENTER, 600, "drive", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, path)

    def explode(*args, **kwargs):
        raise AssertionError("no debería descargar si hay caché")

    monkeypatch.setattr(data_loader, "_download_graph", explode)

    loaded = get_graph(radius_m=600, cache_dir=tmp_path)

    assert loaded.number_of_nodes() == 2
    assert loaded.number_of_edges() == 1


def test_get_graph_raises_when_no_cache_and_download_fails(
    tmp_path, monkeypatch
) -> None:
    def fail(*args, **kwargs):
        raise GraphUnavailableError("sin red")

    monkeypatch.setattr(data_loader, "_download_graph", fail)

    with pytest.raises(GraphUnavailableError):
        get_graph(radius_m=600, cache_dir=tmp_path)


# --- Diagnóstico ----------------------------------------------------------


def test_graph_summary_counts_and_length() -> None:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    graph.add_edge(1, 2, highway="secondary", length=1500.0)
    graph.add_edge(2, 3, highway=["secondary"], length=500.0)
    graph.add_edge(3, 4, highway="residential", length=None)

    summary = graph_summary(graph)

    assert summary["nodes"] == 4
    assert summary["edges"] == 3
    assert summary["total_length_km"] == 2.0
    assert summary["highways"] == {"residential": 1, "secondary": 2}
    assert summary["crs"] == "epsg:4326"


def test_graph_summary_ignores_invalid_lengths() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, highway="secondary", length="no-es-un-numero")

    assert graph_summary(graph)["total_length_km"] == 0.0


# --- Integración real (red) -----------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_OSM_TESTS") != "1",
    reason="descarga real de Overpass; activar con RUN_OSM_TESTS=1",
)
def test_downloads_real_santiago_graph(tmp_path) -> None:
    graph = get_graph(radius_m=600, cache_dir=tmp_path, refresh=True)

    assert graph.number_of_nodes() > 100
    assert graph.number_of_edges() > 100
    assert all(
        is_bike_suitable(attrs) for _, _, attrs in graph.edges(data=True)
    )

    path = cache_path(SANTIAGO_CENTER, 600, "drive", tmp_path)
    metadata_path = path.with_name(f"{path.stem}.meta.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["cache_version"] == CACHE_VERSION
    assert metadata["summary"]["nodes"] == graph.number_of_nodes()
