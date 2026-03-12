import argparse

from vehicle_price_estimator.pipelines.extraction.run_extraction import run_extraction_pipeline


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrae anuncios desde Mercado Libre Colombia.")
    parser.add_argument("--query", default="vehiculos usados colombia", help="Texto de busqueda.")
    parser.add_argument("--limit", type=int, default=None, help="Numero maximo de items a capturar.")
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Evita consultar el detalle individual por item.",
    )
    args = parser.parse_args()

    run_extraction_pipeline(
        query=args.query,
        limit=args.limit,
        fetch_item_details=not args.no_details,
    )
