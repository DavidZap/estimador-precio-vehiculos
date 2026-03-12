import argparse

from vehicle_price_estimator.pipelines.extraction.inventory_capture import (
    DEFAULT_YEAR_ANCHORS,
    run_inventory_capture_campaign,
)


def _parse_csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_year_anchors(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Campana de captura de inventario por marcas, regiones y modelos descubiertos.",
    )
    parser.add_argument(
        "--campaign",
        default="discovery",
        choices=["discovery", "model_region", "year_backfill", "full"],
        help="Tipo de campana a ejecutar.",
    )
    parser.add_argument(
        "--brands",
        default=None,
        help="Lista CSV de codigos de marca. Ej: toyota,mazda,chevrolet",
    )
    parser.add_argument(
        "--regions",
        default=None,
        help="Lista CSV de codigos de region. Ej: bogota,medellin,cali",
    )
    parser.add_argument("--limit", type=int, default=48, help="Limite por consulta.")
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Pausa entre consultas para reducir riesgo de bloqueo.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Limita el numero total de consultas de la campana.",
    )
    parser.add_argument(
        "--min-model-count",
        type=int,
        default=2,
        help="Minimo de anuncios observados para considerar un modelo descubierto.",
    )
    parser.add_argument(
        "--max-models-per-brand",
        type=int,
        default=12,
        help="Maximo de modelos descubiertos por marca para consultas focalizadas.",
    )
    parser.add_argument(
        "--year-anchors",
        default=",".join(str(year) for year in DEFAULT_YEAR_ANCHORS),
        help="Anos ancla CSV para backfill. Ej: 2010,2014,2018,2022,2026",
    )
    parser.add_argument(
        "--with-details",
        action="store_true",
        help="Intenta detalle por item. Para campanas amplias normalmente no conviene.",
    )
    parser.add_argument(
        "--no-process",
        action="store_true",
        help="Solo extrae raw y no ejecuta raw->staging ni staging->core.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo imprime el plan de consultas sin ejecutarlo.",
    )
    args = parser.parse_args()

    plan = run_inventory_capture_campaign(
        campaign=args.campaign,
        brand_codes=_parse_csv_list(args.brands),
        region_codes=_parse_csv_list(args.regions),
        limit=args.limit,
        fetch_item_details=args.with_details,
        process_pipeline=not args.no_process,
        sleep_seconds=args.sleep_seconds,
        dry_run=args.dry_run,
        max_queries=args.max_queries,
        min_model_count=args.min_model_count,
        max_models_per_brand=args.max_models_per_brand,
        year_anchors=_parse_year_anchors(args.year_anchors),
    )

    if args.dry_run:
        print(f"Generated {len(plan)} queries:")
        for query in plan:
            print(
                f"- [{query.phase}] brand={query.brand_code} region={query.region_code} "
                f"model={query.model_hint or '-'} year={query.year_hint or '-'} :: {query.query}"
            )


if __name__ == "__main__":
    main()
