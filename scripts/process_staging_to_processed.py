import argparse

from vehicle_price_estimator.pipelines.processing.staging_to_core import process_staging_to_core


def main() -> None:
    parser = argparse.ArgumentParser(description="Normaliza staging y carga entidades core.")
    parser.add_argument(
        "--extract-run-id",
        default=None,
        help="ID de corrida a procesar. Si se omite, usa el staging mas reciente.",
    )
    args = parser.parse_args()
    process_staging_to_core(extract_run_id=args.extract_run_id)


if __name__ == "__main__":
    main()
