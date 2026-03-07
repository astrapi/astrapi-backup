# helpers/debug.py – Thread-lokaler Debug-Flag
import threading

_local = threading.local()


def set_debug(value: bool) -> None:
    _local.debug = value


def is_debug() -> bool:
    return getattr(_local, "debug", False)
