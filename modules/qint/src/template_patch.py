# achado ao vivo, conferido contra o instalador bash original: cada substituição lá
# é um "sed -i 's|X|Y|' arquivo" -- se X não existe no arquivo, sed não erra, só não
# muda nada. Validar presença aqui era mais rígido que o próprio original, e travava
# em combinações legítimas onde nem todo placeholder previsto existe de fato no
# template real (ex.: sgp não tem a variante sem sufixo de "ocorrencia_comercial").
def patch(text, replacements):
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text
