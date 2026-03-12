import argparse
import json

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
        )
    except ModuleNotFoundError as exc:
        missing_package = getattr(exc, "name", "dependencia_desconocida")
        print(
            "Faltan dependencias de ML para entrenar. "
            f"Instala o actualiza el entorno y vuelve a intentar. Paquete faltante: {missing_package}"
        )
        print("Sugerencia: python -m pip install -e .[dev]")
        raise SystemExit(1) from exc
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
