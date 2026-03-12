import argparse
import json
from pathlib import Path


def _format_cop(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"COP {value:,.0f}"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _print_summary(summary: dict) -> None:
    best_metrics = summary.get("best_metrics", {})
    candidates = sorted(
        summary.get("candidates", []),
        key=lambda item: (
            item.get("metrics", {}).get("mae", float("inf")),
            item.get("metrics", {}).get("rmse", float("inf")),
        ),
    )

    print()
    print("Resumen de entrenamiento")
    print(f"- Dataset: {summary.get('dataset_id')}")
    print(f"- Filas usadas: {summary.get('row_count')}")
    print(f"- Candidatos entrenados: {summary.get('candidate_count')}")
    print(f"- Marcas incluidas: {', '.join(summary.get('include_brands', [])) or 'todas'}")
    print(f"- Minimo de filas por modelo: {summary.get('min_model_rows')}")
    print(f"- Scope del modelo: {summary.get('model_scope', 'global')}")
    print(f"- Mejor modelo: {summary.get('best_model_name')} ({summary.get('best_algorithm')})")
    print(f"- Promovido a produccion: {'si' if summary.get('promoted') else 'no'}")
    print(f"- Dataset guardado en: {summary.get('dataset_path')}")
    print()
    print("Metricas del mejor modelo")
    print(f"- MAE: {_format_cop(best_metrics.get('mae'))}")
    print(f"- RMSE: {_format_cop(best_metrics.get('rmse'))}")
    print(f"- MAPE: {_format_pct(best_metrics.get('mape'))}")
    print(f"- R2: {best_metrics.get('r2', '-')}")
    selected_features = summary.get("best_selected_features", [])
    print(f"- Features seleccionadas: {len(selected_features)}")
    if selected_features:
        print(f"- Primeras features: {', '.join(selected_features[:12])}")
    shap_summary = summary.get("best_shap_summary") or []
    if shap_summary:
        print()
        print("Top SHAP del mejor modelo")
        for item in shap_summary[:10]:
            print(f"- {item.get('feature')}: {item.get('mean_abs_shap')}")
    print()
    print("Ranking de modelos")
    for index, candidate in enumerate(candidates, start=1):
        metrics = candidate.get("metrics", {})
        print(
            f"{index}. {candidate.get('model_name')} [{candidate.get('algorithm')}] | "
            f"MAE={_format_cop(metrics.get('mae'))} | "
            f"RMSE={_format_cop(metrics.get('rmse'))} | "
            f"MAPE={_format_pct(metrics.get('mape'))} | "
            f"R2={metrics.get('r2', '-')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena candidatos de modelo y promueve el mejor si mejora al activo.")
    parser.add_argument("--min-year", type=int, default=2010, help="Ano minimo del vehiculo a considerar.")
    parser.add_argument(
        "--include-outliers",
        action="store_true",
        help="Incluye outliers marcados durante el entrenamiento.",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Incluye anuncios inactivos si existen en core.listings.",
    )
    parser.add_argument(
        "--brands",
        default=None,
        help="Lista CSV de marcas para entrenar un modelo segmentado. Ej: Toyota,Mazda",
    )
    parser.add_argument(
        "--min-model-rows",
        type=int,
        default=1,
        help="Minimo de observaciones por combinacion marca-modelo para incluirla en el dataset.",
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Entrena y registra candidatos sin promover automaticamente el mejor.",
    )
    args = parser.parse_args()

    try:
        from vehicle_price_estimator.pipelines.training.run_training import run_training
    except ModuleNotFoundError as exc:
        missing_package = getattr(exc, "name", "dependencia_desconocida")
        print(
            "Faltan dependencias de ML para entrenar. "
            f"Instala o actualiza el entorno y vuelve a intentar. Paquete faltante: {missing_package}"
        )
        print("Sugerencia: python -m pip install -e .[dev]")
        raise SystemExit(1) from exc

    try:
        summary = run_training(
            min_year=args.min_year,
            exclude_outliers=not args.include_outliers,
            active_only=not args.include_inactive,
            include_brands=[brand.strip() for brand in args.brands.split(",") if brand.strip()] if args.brands else None,
            min_model_rows=args.min_model_rows,
            promote=not args.no_promote,
        )
    except ModuleNotFoundError as exc:
        missing_package = getattr(exc, "name", "dependencia_desconocida")
        print(
            "Faltan dependencias de ML para entrenar. "
            f"Instala o actualiza el entorno y vuelve a intentar. Paquete faltante: {missing_package}"
        )
        print("Sugerencia: python -m pip install -e .[dev]")
        raise SystemExit(1) from exc

    output_dir = Path("data") / "artifacts" / "training" / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{summary.get('dataset_id')}.summary.json"
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    _print_summary(summary)
    print()
    print(f"Resumen completo guardado en: {output_path}")


if __name__ == "__main__":
    main()
