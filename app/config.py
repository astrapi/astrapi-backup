import threading
_local = threading.local()

class Config:
    #dry = False
    #verbose = False
    debug = False
    borg = True
    rsync = True
    proxmox = True


config = Config()

def set_debug(value: bool) -> None:
    _local.debug = value

def is_debug() -> bool:
    return getattr(_local, "debug", config.debug)
