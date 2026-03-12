import argparse

from vehicle_price_estimator.infrastructure.ml.training.trainer import promote_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Promueve manualmente un modelo registrado si mejora al activo.")
    parser.add_argument("--registry-id", required=True, help="UUID del registro en ml.model_registry.")
    args = parser.parse_args()

    promoted = promote_model(args.registry_id)
    if promoted:
        print(f"Modelo {args.registry_id} promovido correctamente.")
    else:
        print(f"Modelo {args.registry_id} no mejora al activo. No fue promovido.")


if __name__ == "__main__":
    main()
