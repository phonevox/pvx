import ipaddress

VALID_PROTOCOLS = {"tcp", "udp", "icmp", "sctp", "dccp", "gre", "ah", "esp"}


def parse_port_spec(spec):
    port_part, _, protocol = spec.partition("/")
    protocol = protocol or None
    if protocol and protocol not in VALID_PROTOCOLS:
        raise ValueError(f"protocolo inválido: {protocol}")

    start_str, _, end_str = port_part.partition("-")
    if not start_str.isdigit() or (end_str and not end_str.isdigit()):
        raise ValueError(f"porta inválida: {spec}")

    start = int(start_str)
    end = int(end_str) if end_str else start
    if not (1 <= start <= 65535) or not (1 <= end <= 65535):
        raise ValueError(f"porta fora do intervalo 1-65535: {spec}")
    if end < start:
        raise ValueError(f"fim da faixa antes do início: {spec}")

    return {"start": start, "end": end, "protocol": protocol}


def validate_cidr(value):
    if "/" in value and not value.rsplit("/", 1)[1].isdigit():
        return False
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return network.version == 4
