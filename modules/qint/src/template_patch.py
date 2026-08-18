def patch(text, replacements):
    missing = [placeholder for placeholder in replacements if placeholder not in text]
    if missing:
        raise ValueError(f"placeholder(s) não encontrado(s) no template: {', '.join(missing)}")

    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text
