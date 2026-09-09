import os

# mesmo caminho usado pelo módulo magnus (ver modules/magnus/src/magnus_ops.py
# MBILLING_WEB_DIR) -- módulos nunca importam uns aos outros, então o caminho é
# replicado aqui.
MBILLING_WEB_DIR = "/var/www/html/mbilling"


def is_magnusbilling():
    return os.path.isdir(MBILLING_WEB_DIR)
