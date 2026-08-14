try:
    from pvx._build_stamp import BRANCH, COMMIT
except ImportError:
    BRANCH = None
    COMMIT = None


def describe():
    if BRANCH is None:
        return None
    label = "nightly" if BRANCH == "dev" else "local"
    return f"{label}, {COMMIT}"
