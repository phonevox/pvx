import socket


def guess_local_ip():
    # connect() num socket UDP não manda pacote nenhum -- só faz o kernel
    # escolher a interface/rota que usaria pra alcançar esse destino.
    # Nenhuma requisição de rede real acontece; não é um IP público de verdade.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return ""
