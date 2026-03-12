import argparse

from vehicle_price_estimator.infrastructure.ml.training.trainer import (
    force_promote_model,
    promote_latest_model_for_scope,
    promote_model,
    promote_preferred_model_for_scope,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promueve manualmente un modelo registrado o el mejor modelo de un scope.")
    parser.add_argument("--registry-id", help="UUID del registro en ml.model_registry.")
    parser.add_argument(
        "--latest-scope",
        choices=["global", "mainstream", "custom"],
        help="Promueve el mejor modelo registrado para ese scope.",
    )
    parser.add_argument(
        "--preferred-algorithm",
        help="Si se usa con --latest-scope, intenta promover el mejor modelo de ese algoritmo dentro del scope.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Fuerza la promocion del modelo indicado por --registry-id, aunque no mejore al activo.",
    )
    args = parser.parse_args()

    if not args.registry_id and not args.latest_scope:
        parser.error("Debes enviar --registry-id o --latest-scope.")

    if args.latest_scope:
        if args.preferred_algorithm:
            promoted_id = promote_preferred_model_for_scope(args.latest_scope, args.preferred_algorithm)
        else:
            promoted_id = promote_latest_model_for_scope(args.latest_scope)
        if promoted_id is None:
            print(f"No hay modelos disponibles para el scope {args.latest_scope}.")
        else:
            if args.preferred_algorithm:
                print(
                    f"Modelo {promoted_id} promovido para el scope {args.latest_scope} "
                    f"priorizando algoritmo {args.preferred_algorithm}."
                )
            else:
                print(f"Modelo {promoted_id} promovido para el scope {args.latest_scope}.")
        return

    promoted = force_promote_model(args.registry_id) if args.force else promote_model(args.registry_id)
    if promoted:
        if args.force:
            print(f"Modelo {args.registry_id} promovido forzadamente.")
        else:
            print(f"Modelo {args.registry_id} promovido correctamente.")
    else:
        print(f"Modelo {args.registry_id} no mejora al activo. No fue promovido.")


if __name__ == "__main__":
    main()
