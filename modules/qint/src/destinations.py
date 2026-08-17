TYPE_LABELS = {"ixcsoft": "IXCSOFT", "sgp": "SGP"}


def destination_specs(tipo):
    suffix = "-ixcsoft" if tipo == "ixcsoft" else ""
    label = TYPE_LABELS[tipo]
    return [
        (f"inicio{suffix}", "s", f"URA - {label} - INICIO"),
        (f"feriado{suffix}", "s", f"URA - {label} - FERIADO"),
        (f"fechado{suffix}", "s", f"URA - {label} - FECHADO"),
        ("from-internal", "${departamento}", f"URA - {label} - FILA"),
    ]
