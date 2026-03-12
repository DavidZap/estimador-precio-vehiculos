import argparse

from vehicle_price_estimator.pipelines.processing.raw_to_staging import process_raw_to_staging


def main() -> None:
    parser = argparse.ArgumentParser(description="Procesa HTML raw de Mercado Libre hacia staging.")
    parser.add_argument(
        "--extract-run-id",
        default=None,
        help="ID de corrida raw a procesar. Si se omite, usa la mas reciente.",
    )
    args = parser.parse_args()
    process_raw_to_staging(extract_run_id=args.extract_run_id)


if __name__ == "__main__":
    main()
