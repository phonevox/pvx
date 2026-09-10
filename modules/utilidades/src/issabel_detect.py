import os

ISSABEL_MARKER_PATH = "/etc/issabel.conf"


def is_issabel():
    return os.path.exists(ISSABEL_MARKER_PATH)
