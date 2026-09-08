import re

# hostname estrito: sem barra, sem espaço, sem metacaractere de shell -- o valor vira
# parte de caminho real (/etc/letsencrypt/live/<dominio>/, <dominio>.conf) e argumento
# de subprocess em lista (nunca shell=True), então isso é o que barra path traversal e
# entrada maliciosa antes de qualquer subprocess/escrita de arquivo.
_LABEL = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
_DOMAIN_RE = re.compile(rf"^{_LABEL}(\.{_LABEL})+$")
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_domain(value):
    if not _DOMAIN_RE.match(value):
        return False
    # certbot/LE não emite certificado pra IP -- rejeita aqui, não deixa o certbot falhar
    # bem mais tarde com um erro menos claro.
    return not _IPV4_RE.match(value)


def is_valid_email(value):
    return bool(_EMAIL_RE.match(value))
