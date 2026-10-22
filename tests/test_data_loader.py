"""Pruebas del cargador de tráfico (Eva).

No requieren geopandas: validan los registros canónicos y la validación.
Ejecutar desde la raíz del repo:  python -m pytest tests/ -q
"""

from __future__ import annotations

import pytest

from app import data_loader
from app.data_loader import (
    CANONICAL_FIELDS,
    CONFIDENCE_LEVELS,
    TRAFFIC_SOURCES,
    confidence_for,
    load_traffic_records,
    to_contract_records,
    validate_traffic_records,
)


@pytest.fixture(scope="module")
def records():
    return load_traffic_records()


def test_carga_los_39_tramos(records):
    assert len(records) == 39


def test_esquema_canonico(records):
    for record in records:
        assert set(record) == set(CANONICAL_FIELDS)
        assert isinstance(record["road_ref"], str) and record["road_ref"]
        assert record["geometry"]["type"] == "LineString"


def test_fuentes_y_reparto(records):
    by_source = {}
    for record in records:
        by_source[record["traffic_source"]] = by_source.get(record["traffic_source"], 0) + 1
    assert by_source == {"xunta": 22, "mitma": 17}
    assert set(by_source) <= set(TRAFFIC_SOURCES)


def test_datos_medidos_sin_huecos(records):
    for record in records:
        assert record["imd"] is not None and record["imd"] > 0
        assert record["heavy_pct"] is not None and 0 <= record["heavy_pct"] <= 100
        assert record["traffic_year"] is not None
        assert record["traffic_confidence"] in CONFIDENCE_LEVELS


def test_anos_reales_de_la_xunta(records):
    xunta_years = {r["traffic_year"] for r in records if r["traffic_source"] == "xunta"}
    mitma_years = {r["traffic_year"] for r in records if r["traffic_source"] == "mitma"}
    # Regresión: la capa antigua marcaba todos los tramos Xunta como 2025.
    assert len(xunta_years) > 1
    assert xunta_years <= {2016, 2019, 2022, 2023, 2024, 2025}
    assert mitma_years == {2022}


def test_reglas_de_confianza(records):
    assert confidence_for("xunta", 2025, 2026) == "high"
    assert confidence_for("xunta", 2023, 2026) == "high"
    assert confidence_for("xunta", 2022, 2026) == "medium"
    assert confidence_for("xunta", 2016, 2026) == "medium"
    assert confidence_for("mitma", 2022, 2026) == "medium"
    assert confidence_for("osm_estimate", None, 2026) == "low"
    # Un dato medido nunca se rebaja a "low".
    for record in records:
        assert record["traffic_confidence"] != "low"


def test_geometrias_en_wgs84(records):
    for record in records:
        for lon, lat in record["geometry"]["coordinates"]:
            assert -180 <= lon <= 180
            assert -90 <= lat <= 90


def test_validacion_sin_errores(records):
    report = validate_traffic_records(records)
    assert report.ok, report.errors
    assert report.warnings == []


def test_detecta_duplicados(records):
    duplicated = [dict(records[0]), dict(records[0])]
    report = validate_traffic_records(duplicated)
    assert not report.ok
    assert any("duplicado" in error for error in report.errors)


def test_estimacion_osm_no_puede_llevar_imd(records):
    estimate = dict(records[0])
    estimate.update(
        imd=None,
        traffic_source="osm_estimate",
        traffic_year=None,
        traffic_confidence="low",
    )
    assert validate_traffic_records([estimate]).ok

    wrong = dict(estimate, imd=1234)
    report = validate_traffic_records([wrong])
    assert not report.ok
    assert any("estimación OSM" in error for error in report.errors)


def test_detecta_imd_invalida(records):
    bad = dict(records[0], imd=0)
    report = validate_traffic_records([bad])
    assert not report.ok


def test_detecta_heavy_pct_fuera_de_rango(records):
    bad = dict(records[0], heavy_pct=120)
    report = validate_traffic_records([bad])
    assert not report.ok


def test_capa_vacia(records):
    assert not validate_traffic_records([]).ok


def test_fichero_ausente(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_traffic_records(tmp_path / "no-existe.geojson")


def test_ruta_independiente_del_directorio_actual(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert len(load_traffic_records()) == 39


def test_to_contract_records_no_comparte_referencias(records):
    copies = to_contract_records(records)
    assert len(copies) == len(records)
    copies[0]["road_ref"] = "CAMBIADO"
    assert records[0]["road_ref"] != "CAMBIADO"


def test_metadatos_de_ruta():
    default = data_loader.resolve_data_path()
    assert default.name == "imd_santiago.geojson"
    assert default.is_absolute()
