"""Carga, normalización y validación de la capa de tráfico medida.

Ámbito: datos (Eva). Este módulo **no** construye el grafo de OSM, ni calcula
Road Stress, ni decide rutas: solo entrega a ``routing`` una capa canónica y
validada que pueda asociarse a las aristas de OSM.

Fuente por defecto: ``data/raw/imd_santiago.geojson``, generada con
``data/build_imd_dataset.py`` a partir de los GeoJSON de Xunta y MITMA.

Esquema canónico (nombres del contrato de API):

===============  =========================================================
``road_ref``     Carretera (``N-550``, ``AC-250``...)
``geometry``     GeoJSON ``LineString`` en EPSG:4326 (``[lon, lat]``)
``imd``          Intensidad media diaria (vehículos/día) o ``None``
``heavy_pct``    % de vehículos pesados (0–100) o ``None``
``traffic_source``  ``xunta`` | ``mitma`` | ``osm_estimate``
``traffic_year`` Año real del aforo o ``None``
``traffic_confidence`` ``high`` | ``medium`` | ``low``
``pk_start``     PK inicial o ``None``
``pk_end``       PK final o ``None``
``corridor``     Nombre del tramo/corredor o ``None``
===============  =========================================================

Regla del proyecto: la ausencia de aforo es ``None``, **nunca** 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = REPO_ROOT / "data" / "raw" / "imd_santiago.geojson"

CANONICAL_FIELDS = (
    "road_ref",
    "geometry",
    "imd",
    "heavy_pct",
    "traffic_source",
    "traffic_year",
    "traffic_confidence",
    "pk_start",
    "pk_end",
    "corridor",
)

TRAFFIC_SOURCES = ("xunta", "mitma", "osm_estimate")
CONFIDENCE_LEVELS = ("high", "medium", "low")

#: Un aforo de la Xunta se considera reciente (``high``) si tiene como mucho
#: estos años. Es una propuesta pendiente de validar con el equipo (AGENTS.md §13).
XUNTA_RECENT_YEARS = 3
MIN_TRAFFIC_YEAR = 1990


class TrafficDataError(ValueError):
    """Error de datos de tráfico (fichero ausente, esquema inválido...)."""


@dataclass
class ValidationReport:
    """Resultado de validar una lista de tramos canónicos."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """``True`` si no hay errores (los avisos no invalidan la capa)."""
        return not self.errors

    def raise_if_invalid(self) -> None:
        if self.errors:
            raise TrafficDataError("; ".join(self.errors))


def _number(value: Any) -> float | None:
    """Convierte a float tolerando ``None``, cadenas vacías y comas decimales."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def source_from_label(label: Any) -> str:
    """Traduce ``Fuente`` del GeoJSON al enum del contrato."""
    if label is None or not str(label).strip():
        raise TrafficDataError("Tramo sin campo 'Fuente'")
    key = str(label).strip().lower()
    if key.startswith("xunta"):
        return "xunta"
    if key.startswith("mitma"):
        return "mitma"
    if "osm" in key:
        return "osm_estimate"
    raise TrafficDataError(f"Fuente de tráfico desconocida: {label!r}")


def confidence_for(
    traffic_source: str, traffic_year: int | None, reference_year: int | None = None
) -> str:
    """Asigna confianza a un dato **medido**.

    - ``xunta`` con año reciente (<= ``XUNTA_RECENT_YEARS``) → ``high``
    - ``xunta`` más antiguo o sin año → ``medium``
    - ``mitma`` (aforo 2022 en el MVP) → ``medium``
    - ``osm_estimate`` → ``low``

    Nunca se marca como ``low`` un dato oficial medido.
    """
    if traffic_source == "osm_estimate":
        return "low"
    if traffic_source == "mitma":
        return "medium"
    if traffic_source == "xunta":
        current = reference_year or date.today().year
        if traffic_year is not None and 0 <= current - traffic_year <= XUNTA_RECENT_YEARS:
            return "high"
        return "medium"
    raise TrafficDataError(f"traffic_source desconocido: {traffic_source!r}")


def _normalize_feature(feature: dict, index: int) -> dict:
    """Convierte una ``Feature`` del GeoJSON al esquema canónico."""
    if not isinstance(feature, dict):
        raise TrafficDataError(f"Tramo #{index}: no es un objeto GeoJSON")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise TrafficDataError(f"Tramo #{index}: se esperaba geometría LineString")

    props = feature.get("properties") or {}
    road_ref = props.get("Estrada")
    if not isinstance(road_ref, str) or not road_ref.strip():
        raise TrafficDataError(f"Tramo #{index}: falta 'Estrada'")

    imd_value = _number(props.get("IMD"))
    heavy_value = _number(props.get("Pct_pesados"))
    year_value = _number(props.get("Anio"))
    source = source_from_label(props.get("Fuente"))
    year = int(year_value) if year_value is not None else None

    return {
        "road_ref": road_ref.strip().upper(),
        "geometry": geometry,
        "imd": int(round(imd_value)) if imd_value is not None else None,
        "heavy_pct": round(heavy_value, 2) if heavy_value is not None else None,
        "traffic_source": source,
        "traffic_year": year,
        "traffic_confidence": confidence_for(source, year),
        "pk_start": _number(props.get("PK_inicio")),
        "pk_end": _number(props.get("PK_fin")),
        "corridor": (props.get("Corredor") or None),
    }


def resolve_data_path(path: str | Path | None = None) -> Path:
    """Devuelve la ruta de la capa, absoluta e independiente del directorio actual."""
    return Path(path).expanduser().resolve() if path else DEFAULT_DATA_PATH


@lru_cache(maxsize=8)
def _read_features(path: str, mtime_ns: int, size: int) -> dict:
    """Lee el GeoJSON (cacheado por ruta + mtime + tamaño)."""
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    if isinstance(document, list):  # tolera listas de features sueltas
        return {"type": "FeatureCollection", "features": document}
    if document.get("type") != "FeatureCollection":
        raise TrafficDataError(f"{path}: se esperaba un FeatureCollection")
    return document


def load_traffic_records(path: str | Path | None = None) -> list[dict]:
    """Carga la capa y devuelve una lista de tramos canónicos.

    Cada tramo incluye ``geometry`` como dict GeoJSON (``[lon, lat]``), listo
    para ``shapely.geometry.shape``. Levanta ``FileNotFoundError`` con un
    mensaje claro si la capa no está en el repo.
    """
    data_path = resolve_data_path(path)
    if not data_path.exists():
        raise FileNotFoundError(
            f"No existe la capa de tráfico en {data_path}. "
            "Recupérala con `git checkout main -- data/raw/imd_santiago.geojson` "
            "o genérala con `python data/build_imd_dataset.py`."
        )

    stat = data_path.stat()
    document = _read_features(str(data_path), stat.st_mtime_ns, stat.st_size)
    return [
        _normalize_feature(feature, index)
        for index, feature in enumerate(document.get("features", []))
    ]


def load_traffic_segments(path: str | Path | None = None):
    """Devuelve un ``GeoDataFrame`` (EPSG:4326) con el esquema canónico.

    Requiere ``geopandas`` (dependencia del backend). Si no está instalado,
    se puede usar ``load_traffic_records()``, que solo necesita la librería
    estándar.
    """
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ImportError(
            "load_traffic_segments() necesita geopandas. "
            "Instálalo con `pip install geopandas` o usa load_traffic_records()."
        ) from exc

    from shapely.geometry import shape

    records = load_traffic_records(path)
    if not records:
        raise TrafficDataError("La capa de tráfico no contiene tramos")

    columns = {name: [record[name] for record in records] for name in CANONICAL_FIELDS if name != "geometry"}
    frame = gpd.GeoDataFrame(
        columns,
        geometry=[shape(record["geometry"]) for record in records],
        crs="EPSG:4326",
    )
    return frame[list(CANONICAL_FIELDS)]


def to_contract_records(records: list[dict] | None = None, path: str | Path | None = None) -> list[dict]:
    """Devuelve copias de los tramos con los nombres del contrato de API."""
    base = load_traffic_records(path) if records is None else records
    return [dict(record) for record in base]


def validate_traffic_records(records: list[dict]) -> ValidationReport:
    """Valida tipos, rangos, geometrías y duplicados de una capa canónica."""
    report = ValidationReport()
    if not records:
        report.errors.append("La capa de tráfico está vacía")
        return report

    current_year = date.today().year
    seen: dict[tuple, int] = {}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            report.errors.append(f"Tramo #{index}: no es un diccionario")
            continue
        label = f"Tramo #{index} ({record.get('road_ref') or 'sin carretera'})"

        missing = [name for name in CANONICAL_FIELDS if name not in record]
        if missing:
            report.errors.append(f"{label}: faltan campos {', '.join(missing)}")
            continue

        geometry = record["geometry"]
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            report.errors.append(f"{label}: geometría distinta de LineString")
        else:
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) < 2:
                report.errors.append(f"{label}: LineString con menos de 2 puntos")
            for point in coordinates:
                if (
                    not isinstance(point, (list, tuple))
                    or len(point) < 2
                    or any(_number(value) is None for value in point[:2])
                ):
                    report.errors.append(f"{label}: coordenada malformada")
                    break
                lon, lat = float(point[0]), float(point[1])
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    report.errors.append(f"{label}: coordenada fuera de rango [{lon}, {lat}]")
                    break

        road_ref = record["road_ref"]
        if not isinstance(road_ref, str) or not road_ref.strip():
            report.errors.append(f"{label}: 'road_ref' vacío")
        elif road_ref != road_ref.strip().upper():
            report.warnings.append(f"{label}: 'road_ref' no está normalizado a mayúsculas")

        source = record["traffic_source"]
        if source not in TRAFFIC_SOURCES:
            report.errors.append(f"{label}: traffic_source inválido {source!r}")
            source = None

        imd = record["imd"]
        heavy = record["heavy_pct"]
        year = record["traffic_year"]

        if imd is None:
            if source in ("xunta", "mitma"):
                report.errors.append(f"{label}: dato medido sin IMD")
        elif not isinstance(imd, (int, float)) or isinstance(imd, bool) or imd <= 0:
            report.errors.append(f"{label}: IMD inválida {imd!r}")
        elif imd > 1_000_000:
            report.warnings.append(f"{label}: IMD sospechosamente alta ({imd})")

        if heavy is not None:
            if not isinstance(heavy, (int, float)) or isinstance(heavy, bool) or not (0 <= heavy <= 100):
                report.errors.append(f"{label}: heavy_pct fuera de 0–100 ({heavy!r})")
            elif imd is None:
                report.warnings.append(f"{label}: heavy_pct sin IMD")

        if year is None:
            if source in ("xunta", "mitma"):
                report.warnings.append(f"{label}: dato medido sin año")
        elif not isinstance(year, int) or isinstance(year, bool) or not (MIN_TRAFFIC_YEAR <= year <= current_year + 1):
            report.errors.append(f"{label}: traffic_year fuera de rango ({year!r})")

        if source == "osm_estimate" and (imd is not None or year is not None):
            report.errors.append(f"{label}: una estimación OSM no puede llevar IMD ni año")

        confidence = record["traffic_confidence"]
        if confidence not in CONFIDENCE_LEVELS:
            report.errors.append(f"{label}: traffic_confidence inválido {confidence!r}")
        elif source is not None:
            expected = confidence_for(source, year, current_year)
            if confidence != expected:
                report.warnings.append(
                    f"{label}: confianza {confidence!r} distinta de la esperada {expected!r}"
                )

        pk_start, pk_end = record["pk_start"], record["pk_end"]
        if pk_start is None and pk_end is None:
            report.warnings.append(f"{label}: sin PK de inicio ni fin")
        elif pk_start is None or pk_end is None:
            report.warnings.append(f"{label}: PK incompleto")
        elif pk_start >= pk_end:
            report.errors.append(f"{label}: PK_inicio ({pk_start}) >= PK_fin ({pk_end})")

        corridor = record["corridor"]
        if corridor is not None and not isinstance(corridor, str):
            report.warnings.append(f"{label}: 'corridor' no es texto")

        if pk_start is not None and pk_end is not None:
            key = (road_ref, float(pk_start), float(pk_end))
            if key in seen:
                report.errors.append(
                    f"{label}: duplicado del tramo #{seen[key]} (misma carretera y PK)"
                )
            else:
                seen[key] = index

    return report
