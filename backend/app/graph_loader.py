"""Carga del grafo viario de OpenStreetMap para Cycle Escape.

Responsabilidades de esta fase:

- descargar la red de OSMnx alrededor de un origen;
- descartar vías no aptas o ilegales para bicicleta;
- quedarse con la componente conexa principal;
- cachear el resultado en local para no depender de internet en la demo.

El grafo se guarda sin proyectar (EPSG:4326) porque las geometrías deben viajar
como GeoJSON. La longitud de cada arista (``length``) ya viene en metros.

Nota sobre Overpass: el endpoint público por defecto de OSMnx suele estar
saturado y algunos mirrors filtran por ``User-Agent``/``Referer``. Por eso se
configuran explícitamente y se puede forzar otro endpoint con la variable de
entorno ``CYCLE_ESCAPE_OVERPASS_URL``.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import networkx as nx
import osmnx as ox

logger = logging.getLogger(__name__)

#: Centro de la demo (Santiago de Compostela). Es configuración, no una constante
#: del algoritmo: ``get_graph`` acepta cualquier centro.
SANTIAGO_CENTER: tuple[float, float] = (42.8782, -8.5448)

#: Radio del área de descarga. Cubre el anillo de candidatos de 8-12 km.
DEFAULT_RADIUS_M = 12_000

DEFAULT_NETWORK_TYPE = "drive"

#: Súbese cuando cambie el filtrado o el formato de caché, para invalidarla.
CACHE_VERSION = 2


#: Endpoints probados en orden hasta que uno responda.
DEFAULT_OVERPASS_ENDPOINTS: tuple[str, ...] = (
    "https://overpass.openstreetmap.fr/api",
    "https://overpass-api.de/api",
)

HTTP_USER_AGENT = "CycleEscape-Hackathon/0.1 (demo)"
HTTP_REFERER = "https://github.com/xiannovoa/cycle-escape"

#: ``tmp/`` ya está ignorado por Git; el grafo no debe versionarse.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "tmp" / "osm"

#: Vías que un ciclista de carretera no puede o no debe usar.
FORBIDDEN_HIGHWAYS = frozenset(
    {
        "motorway",
        "motorway_link",
        "busway",
        "raceway",
        "bus_guideway",
        "construction",
        "proposed",
        "abandoned",
        "platform",
    }
)

#: Accesos que implican prohibición salvo que la bici esté permitida explícitamente.
FORBIDDEN_ACCESS = frozenset({"no", "private"})

#: Valores de ``bicycle`` que autorizan el paso aunque el acceso sea restringido.
EXPLICIT_BICYCLE_YES = frozenset({"yes", "designated", "permissive"})


class GraphUnavailableError(RuntimeError):
    """No hay caché y ningún endpoint de Overpass ha respondido."""


def _text(value: Any) -> str | None:
    """Normaliza un valor OSM (escalar o lista) a texto en minúsculas."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    return str(value).strip().lower() or None


def is_bike_suitable(attrs: Mapping[str, Any]) -> bool:
    """Decide si una arista OSM es apta para una bicicleta de carretera.

    Se eliminan autopistas y vías prohibidas. ``trunk`` y ``primary`` se
    mantienen: en España muchas veces son carreteras convencionales legales
    para bicicleta; su penalización llega con el Road Stress, no con el filtro.
    """
    highway = _text(attrs.get("highway"))
    if highway is None or highway in FORBIDDEN_HIGHWAYS:
        return False
    if highway.startswith("motorway"):
        return False

    bicycle = _text(attrs.get("bicycle"))
    if bicycle == "no":
        return False
    explicit_yes = bicycle in EXPLICIT_BICYCLE_YES

    access = _text(attrs.get("access"))
    if access in FORBIDDEN_ACCESS and not explicit_yes:
        return False

    vehicle = _text(attrs.get("vehicle"))
    if vehicle == "no" and not explicit_yes:
        return False

    if _text(attrs.get("motorroad")) == "yes" and not explicit_yes:
        return False

    return True


def filter_bike_unsuitable(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Elimina aristas no aptas para bici y los nodos que quedan aislados.

    Modifica el grafo recibido (OSMnx trabaja así por convención) y lo devuelve.
    """
    unsuitable = [
        (u, v, key)
        for u, v, key, attrs in G.edges(keys=True, data=True)
        if not is_bike_suitable(attrs)
    ]
    G.remove_edges_from(unsuitable)

    isolated = list(nx.isolates(G))
    G.remove_nodes_from(isolated)

    logger.info(
        "Filtrado ciclista: %d aristas no aptas y %d nodos aislados eliminados",
        len(unsuitable),
        len(isolated),
    )
    return G


def keep_largest_component(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Se queda con la mayor componente débilmente conexa del grafo."""
    return ox.truncate.largest_component(G, strongly=False)


def cache_path(
    center: tuple[float, float] = SANTIAGO_CENTER,
    radius_m: int = DEFAULT_RADIUS_M,
    network_type: str = DEFAULT_NETWORK_TYPE,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Path:
    """Ruta determinista del GraphML cacheado para un área concreta."""
    lat, lon = center
    filename = (
        f"graph_{lat:.4f}_{lon:.4f}_r{radius_m}_{network_type}"
        f"_v{CACHE_VERSION}.graphml"
    )
    return Path(cache_dir) / filename


def graph_summary(G: nx.MultiDiGraph) -> dict[str, Any]:
    """Resumen legible del grafo para diagnóstico y para ``/api/health``."""
    total_length_m = 0.0
    highways: Counter[str] = Counter()

    for _, _, attrs in G.edges(data=True):
        try:
            total_length_m += float(attrs.get("length") or 0.0)
        except (TypeError, ValueError):
            pass
        highways[_text(attrs.get("highway")) or "desconocido"] += 1

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "total_length_km": round(total_length_m / 1000.0, 1),
        "highways": dict(sorted(highways.items())),
        "crs": G.graph.get("crs"),
    }


def configure_osmnx(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    """Ajusta OSMnx para que sea usable en el hackathon sin ensuciar el repo."""
    overpass_cache = Path(cache_dir) / "overpass"
    overpass_cache.mkdir(parents=True, exist_ok=True)

    ox.settings.http_user_agent = HTTP_USER_AGENT
    ox.settings.http_referer = HTTP_REFERER
    ox.settings.requests_timeout = 180
    ox.settings.cache_folder = str(overpass_cache)
    ox.settings.use_cache = True
    ox.settings.log_console = False


def _overpass_endpoints() -> tuple[str, ...]:
    """Endpoints a probar, con posibilidad de forzar uno por entorno."""
    override = os.getenv("CYCLE_ESCAPE_OVERPASS_URL")
    if override:
        return (override,)
    return DEFAULT_OVERPASS_ENDPOINTS


def _download_graph(
    center: tuple[float, float],
    radius_m: int,
    network_type: str,
    endpoints: Iterable[str],
) -> nx.MultiDiGraph:
    last_error: Exception | None = None

    for endpoint in endpoints:
        try:
            ox.settings.overpass_url = endpoint
            logger.info(
                "Descargando grafo (%.4f, %.4f), radio %d m, tipo %s desde %s",
                center[0],
                center[1],
                radius_m,
                network_type,
                endpoint,
            )
            return ox.graph_from_point(
                center,
                dist=radius_m,
                dist_type="bbox",
                network_type=network_type,
                simplify=True,
                retain_all=False,
            )
        except Exception as exc:  # red, timeout, 429, 403, respuesta inválida...
            last_error = exc
            logger.warning("Endpoint %s falló: %s", endpoint, exc)

    raise GraphUnavailableError(
        "No se pudo descargar el grafo de OSM desde ningún endpoint y no hay "
        "caché disponible. Comprueba la conexión o define "
        "CYCLE_ESCAPE_OVERPASS_URL."
    ) from last_error


def _write_metadata(
    metadata_path: Path,
    center: tuple[float, float],
    radius_m: int,
    network_type: str,
    summary: Mapping[str, Any],
) -> None:
    payload = {
        "cache_version": CACHE_VERSION,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "center": {"lat": center[0], "lon": center[1]},
        "radius_m": radius_m,
        "network_type": network_type,
        "summary": dict(summary),
    }
    metadata_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_graph(
    center: tuple[float, float] = SANTIAGO_CENTER,
    radius_m: int = DEFAULT_RADIUS_M,
    network_type: str = DEFAULT_NETWORK_TYPE,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> nx.MultiDiGraph:
    """Devuelve el grafo viario apto para bici, desde caché o desde Overpass.

    Args:
        center: ``(lat, lon)`` del centro del área.
        radius_m: radio del área de descarga en metros.
        network_type: tipo de red de OSMnx (``drive`` por defecto).
        cache_dir: carpeta local para el GraphML y la caché de Overpass.
        refresh: ignorar la caché existente y volver a descargar.
    """
    if radius_m <= 0:
        raise ValueError("radius_m debe ser positivo")

    cache_dir = Path(cache_dir)
    path = cache_path(center, radius_m, network_type, cache_dir)
    metadata_path = path.with_name(f"{path.stem}.meta.json")

    if path.exists() and not refresh:
        logger.info("Cargando grafo desde caché: %s", path)
        return ox.load_graphml(path)

    configure_osmnx(cache_dir)

    graph = _download_graph(center, radius_m, network_type, _overpass_endpoints())
    logger.info(
        "Descargado: %d nodos, %d aristas", graph.number_of_nodes(), graph.number_of_edges()
    )

    graph = filter_bike_unsuitable(graph)
    graph = keep_largest_component(graph)

    path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, path)
    summary = graph_summary(graph)
    _write_metadata(metadata_path, center, radius_m, network_type, summary)
    logger.info("Grafo cacheado en %s", path)

    return graph


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    graph = get_graph()
    print(json.dumps(graph_summary(graph), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
