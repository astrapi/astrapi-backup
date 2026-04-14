"""Helpers for resolving Remote Device SSH configuration"""


def get_remote(remote_id: int | str) -> dict | None:
    """Get a single remote device by ID"""
    from astrapi.core.system.db import load_config
    remotes = load_config("remotes") or {}
    return remotes.get(str(remote_id))


def get_remote_ssh(remote_id: int | str) -> tuple[str, str, int]:
    """
    Get SSH connection info from a Remote Device.

    Args:
        remote_id: Remote Device ID

    Returns:
        (host, ssh_user, ssh_port)

    Raises:
        ValueError if remote not found or disabled
    """
    if str(remote_id) == "local":
        return ("local", "backupadm", 22)

    remote = get_remote(remote_id)
    if not remote:
        raise ValueError(f"Remote Device '{remote_id}' not found")

    if not remote.get("enabled"):
        raise ValueError(f"Remote Device '{remote_id}' is disabled")

    host = remote.get("host")
    if not host:
        raise ValueError(f"Remote Device '{remote_id}': No host configured")

    ssh_user = remote.get("ssh_user")
    ssh_port = int(remote.get("ssh_port") or 22)

    return (host, ssh_user, ssh_port)


def get_all_remotes_for_select(type_filter: str | None = None, include_local: bool = True) -> list[dict]:
    """Get all enabled remote devices for dropdown selection.

    Args:
        type_filter:   optional type key (e.g. "borg_source", "proxmox_node").
                       If given, only remotes that include this type are returned.
        include_local: if True (default), prepends a "Lokal" option.
    """
    from astrapi.core.system.db import load_config
    remotes = load_config("remotes") or {}

    result = [{"id": "local", "label": "Lokal"}] if include_local else []
    for remote_id, remote in remotes.items():
        if not remote.get("enabled"):
            continue
        if type_filter:
            types = remote.get("types") or []
            if isinstance(types, str):
                types = [t for t in types.split("\n") if t]
            if type_filter not in types:
                continue
        result.append({
            "id":       remote_id,
            "label":    remote.get("host"),
            "host":     remote.get("host"),
            "ssh_user": remote.get("ssh_user"),
            "ssh_port": remote.get("ssh_port", 22),
        })

    return result
