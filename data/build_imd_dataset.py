#!/usr/bin/env python3
"""Xera a capa IMD unificada de Santiago a partir dos datos crúos.

Uso:
    python data/build_imd_dataset.py
    python data/build_imd_dataset.py --out data/raw/imd_santiago.geojson

Entrada:
    data/raw/xunta/AC-*.geojson          (Xunta de Galicia, IMD por tramo)
    data/raw/mitma/mitma_santiago.geojson (MITMA, N-550 / N-525 / N-634)

Saída (por defecto data/raw/imd_santiago.geojson):
    Estrada, Corredor, PK_inicio, PK_fin, IMD, Pct_pesados, Anio, Fuente, Nivel

O ano (`Anio`) é o ano REAL da observación, non o ano da edición do dataset:
para a Xunta sácase de `Anho_afo_u` (pode ir de 2016 a 2025) e para MITMA de
`Anio` (2022). `Fuente` identifica só a fonte: `Xunta` ou `MITMA`.

Este script non modifica os ficheiros de orixe.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_XUNTA_DIR = DATA_DIR / "raw" / "xunta"
DEFAULT_MITMA_PATH = DATA_DIR / "raw" / "mitma" / "mitma_santiago.geojson"
DEFAULT_OUT_PATH = DATA_DIR / "raw" / "imd_santiago.geojson"

# Niveis de tráfico para ciclistas (mesmos umbrais que usa o frontend).
LEVELS = (
    (2000, "tranquila"),
    (5000, "moderada"),
    (10000, "alta"),
)


def num(value: Any) -> float | None:
    """Converte a float tolerando None, cadeas baleiras e comas decimais."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def nivel(imd: float | None) -> str | None:
    if imd is None:
        return None
    for limit, name in LEVELS:
        if imd < limit:
            return name
    return "muy_alta"


def xunta_feature(feature: dict, source: Path) -> dict:
    props = feature.get("properties") or {}
    imd = num(props.get("IMD_2025", props.get("IMD")))
    heavy = num(props.get("P_porcenta", props.get("Pct_pesados")))
    # Algunhas capas traen os pesados en vehículos/día en vez de %.
    if heavy is not None and imd and heavy > 100:
        heavy = round(heavy / imd * 100, 2)
    year = num(props.get("Anho_afo_u"))
    return {
        "type": "Feature",
        "geometry": feature["geometry"],
        "properties": {
            "Estrada": props.get("Estrada"),
            "Corredor": props.get("Treito") or props.get("Denominaci"),
            "PK_inicio": num(props.get("Pq_inicio")),
            "PK_fin": num(props.get("Pq_fin")),
            "IMD": int(round(imd)) if imd is not None else None,
            "Pct_pesados": round(heavy, 2) if heavy is not None else None,
            "Anio": int(year) if year is not None else None,
            "Fuente": "Xunta",
            "Nivel": nivel(imd),
        },
        "_source_file": source.name,
    }


def mitma_feature(feature: dict, source: Path) -> dict:
    props = feature.get("properties") or {}
    imd = num(props.get("IMD"))
    heavy = num(props.get("Pct_pesados"))
    year = num(props.get("Anio"))
    return {
        "type": "Feature",
        "geometry": feature["geometry"],
        "properties": {
            "Estrada": props.get("Estrada"),
            "Corredor": props.get("Corredor"),
            "PK_inicio": num(props.get("PK_inicio")),
            "PK_fin": num(props.get("PK_fin")),
            "IMD": int(round(imd)) if imd is not None else None,
            "Pct_pesados": round(heavy, 2) if heavy is not None else None,
            "Anio": int(year) if year is not None else None,
            "Fuente": "MITMA",
            "Nivel": nivel(imd),
        },
        "_source_file": source.name,
    }


def build(xunta_dir: Path, mitma_path: Path) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    features: list[dict] = []

    xunta_files = sorted(xunta_dir.glob("AC-*.geojson"))
    if not xunta_files:
        raise FileNotFoundError(f"Non hai ficheiros AC-*.geojson en {xunta_dir}")
    for path in xunta_files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for feature in doc.get("features", []):
            features.append(xunta_feature(feature, path))

    if not mitma_path.exists():
        raise FileNotFoundError(f"Non existe {mitma_path}")
    doc = json.loads(mitma_path.read_text(encoding="utf-8"))
    for feature in doc.get("features", []):
        features.append(mitma_feature(feature, mitma_path))

    for i, feature in enumerate(features):
        props = feature["properties"]
        label = f"#{i} {props.get('Estrada')} PK {props.get('PK_inicio')}-{props.get('PK_fin')}"
        if props["IMD"] is None:
            warnings.append(f"{label}: sen IMD")
        if props["Anio"] is None:
            warnings.append(f"{label}: sen ano de aforo")
        if props["Pct_pesados"] is None:
            warnings.append(f"{label}: sen % de pesados")
        feature.pop("_source_file", None)

    return features, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xunta-dir", type=Path, default=DEFAULT_XUNTA_DIR)
    parser.add_argument("--mitma", type=Path, default=DEFAULT_MITMA_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    args = parser.parse_args()

    features, warnings = build(args.xunta_dir, args.mitma)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"{args.out}: {len(features)} tramos")
    counts: dict[str, int] = {}
    for feature in features:
        props = feature["properties"]
        key = f"{props['Fuente']} {props['Anio']}"
        counts[key] = counts.get(key, 0) + 1
    for key, count in sorted(counts.items()):
        print(f"  {key}: {count} tramos")
    for warning in warnings:
        print(f"AVISO {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
