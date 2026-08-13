REQUIRED_FIELDS = ("name", "version", "entrypoint")


def validate_manifest(manifest):
    missing = [field for field in REQUIRED_FIELDS if not manifest.get(field)]
    if missing:
        raise ValueError(f"manifest.json sem campo(s) obrigatório(s): {', '.join(missing)}")
    return True
