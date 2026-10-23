"""Tests del enriquecimiento del grafo con la capa de tráfico medida."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import LineString

from app.graph_loader import SANTIAGO_CENTER, cache_path, get_graph
from app.scoring import score_graph_edges
from app.traffic_enrichment import (
    EnrichmentReport,
    TrafficEnrichmentError,
    enrich_graph_with_traffic,
)

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "imd_santiago.geojson"

LON, LAT = -8.55, 42.88


def add_edge(
    G: nx.MultiDiGraph,
    u: int,
    v: int,
    *,
    ref: str,
    lat_offset: float = 0.0,
    length_m: float = 800.0,
) -> None:
    G.add_node(u, x=LON, y=LAT + lat_offset)
    G.add_node(v, x=LON + 0.01, y=LAT + lat_offset)
    G.add_edge(
        u,
        v,
        key=0,
        length=length_m,
        highway="secondary",
        maxspeed="70",
        lanes="2",
        surface="asphalt",
        ref=ref,
        geometry=LineString(
            [
                (LON, LAT + lat_offset),
                (LON + 0.01, LAT + lat_offset),
            ]
        ),
    )


def build_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    add_edge(G, 1, 2, ref="AC-543")
    # Carretera distinta, paralela y a ~11 m: no debe casar por proximidad.
    add_edge(G, 3, 4, ref="N-550", lat_offset=0.0001)
    return G


def traffic_frame(records: list[dict]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


def traffic_record(**overrides) -> dict:
    record = {
        "road_ref": "AC-543",
        "imd": 5000,
        "heavy_pct": 5.0,
        "traffic_source": "xunta",
        "traffic_year": 2025,
        "traffic_confidence": "high",
        "pk_start": 0.0,
        "pk_end": 1.0,
        "geometry": LineString([(LON, LAT), (LON + 0.01, LAT)]),
    }
    record.update(overrides)
    return record


# --- Matching -------------------------------------------------------------


def test_matches_edge_by_ref_and_distance() -> None:
    G = build_graph()

    report = enrich_graph_with_traffic(
        G, traffic_frame([traffic_record()])
    )

    assert report.matched_edges == 1
    assert report.matched_segments == 1
    assert report.sources == ("xunta",)
    assert report.missing_segments == ()

    attrs = G[1][2][0]
    assert attrs["imd"] == 5000
    assert attrs["heavy_pct"] == 5.0
    assert attrs["traffic_source"] == "xunta"
    assert attrs["traffic_year"] == 2025
    assert attrs["traffic_confidence"] == "high"

    # La paralela con otra ref no se enriquece.
    assert "imd" not in G[3][4][0]


def test_does_not_match_without_compatible_ref() -> None:
    G = build_graph()
    traffic = traffic_frame([traffic_record(road_ref="AC-999")])

    report = enrich_graph_with_traffic(G, traffic)

    assert report.matched_edges == 0
    assert report.sources == ()
    assert "imd" not in G[1][2][0]
    assert report.missing_segments


def test_does_not_match_beyond_buffer() -> None:
    G = build_graph()
    far_geometry = LineString([(LON, LAT + 0.001), (LON + 0.01, LAT + 0.001)])
    traffic = traffic_frame([traffic_record(geometry=far_geometry)])

    report = enrich_graph_with_traffic(G, traffic)

    assert report.matched_edges == 0
    assert report.missing_segments


def test_nearest_segment_wins() -> None:
    G = build_graph()
    near = traffic_record(imd=5000)
    far_geometry = LineString([(LON, LAT + 0.0002), (LON + 0.01, LAT + 0.0002)])
    far = traffic_record(imd=9000, geometry=far_geometry)

    enrich_graph_with_traffic(G, traffic_frame([far, near]))

    assert G[1][2][0]["imd"] == 5000


def test_higher_confidence_wins_on_equal_distance() -> None:
    G = build_graph()
    high = traffic_record(imd=5000, traffic_confidence="high")
    medium = traffic_record(imd=9000, traffic_confidence="medium")

    enrich_graph_with_traffic(G, traffic_frame([medium, high]))

    assert G[1][2][0]["imd"] == 5000
    assert G[1][2][0]["traffic_confidence"] == "high"


def test_report_counts_and_lengths() -> None:
    G = build_graph()
    traffic = traffic_frame(
        [traffic_record(), traffic_record(road_ref="N-550", pk_start=1, pk_end=2)]
    )

    report = enrich_graph_with_traffic(G, traffic)

    assert report.matched_edges == 2
    assert report.total_edges == 2
    assert report.matched_length_km == pytest.approx(1.6)
    assert report.total_length_km == pytest.approx(1.6)
    assert report.matched_share == pytest.approx(1.0)


def test_long_segment_matches_several_edges() -> None:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    add_edge(G, 1, 2, ref="AC-543", length_m=400)
    G.add_node(3, x=LON + 0.01, y=LAT)
    G.add_node(4, x=LON + 0.02, y=LAT)
    G.add_edge(
        2,
        3,
        key=0,
        length=800,
        highway="secondary",
        maxspeed="70",
        lanes="2",
        surface="asphalt",
        ref="AC-543",
        geometry=LineString([(LON + 0.01, LAT), (LON + 0.02, LAT)]),
    )
    traffic = traffic_frame(
        [
            traffic_record(
                geometry=LineString([(LON, LAT), (LON + 0.02, LAT)])
            )
        ]
    )

    report = enrich_graph_with_traffic(G, traffic)

    assert report.matched_edges == 2
    assert G[1][2][0]["imd"] == 5000
    assert G[2][3][0]["imd"] == 5000


# --- Validación y reporte -------------------------------------------------


def test_requires_canonical_columns() -> None:
    G = build_graph()
    traffic = traffic_frame([traffic_record()]).drop(columns=["imd"])

    with pytest.raises(TrafficEnrichmentError):
        enrich_graph_with_traffic(G, traffic)


def test_empty_traffic_returns_zero_report() -> None:
    G = build_graph()
    traffic = gpd.GeoDataFrame(
        columns=[
            "road_ref",
            "imd",
            "heavy_pct",
            "traffic_source",
            "traffic_year",
            "traffic_confidence",
            "geometry",
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )

    report = enrich_graph_with_traffic(G, traffic)

    assert report == EnrichmentReport(
        matched_edges=0,
        total_edges=2,
        matched_segments=0,
        total_segments=0,
        matched_length_km=0.0,
        total_length_km=1.6,
        sources=(),
        missing_segments=(),
    )


def test_missing_segment_is_reported() -> None:
    G = build_graph()
    traffic = traffic_frame(
        [traffic_record(road_ref="AC-999", pk_start=3.5, pk_end=4.0)]
    )

    report = enrich_graph_with_traffic(G, traffic)

    assert report.missing_segments == ("AC-999 PK 3.5-4",)


def test_enrichment_invalidates_scoring() -> None:
    G = build_graph()
    G.graph["cycle_escape_scored"] = True

    enrich_graph_with_traffic(G, traffic_frame([traffic_record()]))

    assert G.graph["cycle_escape_scored"] is False


def test_repeated_enrichment_clears_stale_measurements() -> None:
    G = build_graph()
    enrich_graph_with_traffic(G, traffic_frame([traffic_record()]))
    assert G[1][2][0]["imd"] == 5000

    enrich_graph_with_traffic(
        G, traffic_frame([traffic_record(road_ref="AC-999")])
    )

    assert "imd" not in G[1][2][0]
    assert "traffic_source" not in G[1][2][0]


def test_scoring_after_enrichment_uses_measured_traffic() -> None:
    G = build_graph()
    before = G[1][2][0]["highway"]
    enrich_graph_with_traffic(G, traffic_frame([traffic_record()]))

    score_graph_edges(G)

    attrs = G[1][2][0]
    assert attrs["highway"] == before
    assert attrs["traffic_source"] == "xunta"
    assert attrs["traffic_confidence"] == "high"
    assert attrs["road_stress"] > 0
    assert attrs["quiet_score"] == pytest.approx(100 - attrs["road_stress"], abs=0.1)
    assert G.graph["cycle_escape_scored"] is True


# --- Integración con la capa real ----------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not cache_path().exists() or not DATA_PATH.exists(),
    reason="requiere grafo cacheado y capa IMD real",
)
def test_real_traffic_enrichment() -> None:
    graph = get_graph()

    report = enrich_graph_with_traffic(graph)

    assert report.total_segments == 39
    assert report.matched_segments >= 25
    assert report.matched_edges > 1_000
    assert report.matched_length_km > 100
    assert {"xunta", "mitma"} <= set(report.sources)
    assert report.missing_segments
    assert report.total_length_km > 4_000

    score_graph_edges(graph)

    measured = [
        attrs
        for _, _, attrs in graph.edges(data=True)
        if attrs.get("imd") is not None
    ]
    assert measured
    assert all(
        attrs["traffic_source"] in {"xunta", "mitma"} for attrs in measured
    )
    assert all(attrs["road_stress"] >= 0 for attrs in measured)
    assert any(attrs["imd"] > 20_000 for attrs in measured)
