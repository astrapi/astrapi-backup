"""Helpers for resolving Remote Device SSH configuration"""


def get_remote(remote_id: int | str) -> dict | None:
    """Get a single remote device by ID"""
    from core.system.db import load_config
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
    ssh_port = int(remote.get("ssh_port", 22))

    return (host, ssh_user, ssh_port)


def get_all_remotes_for_select() -> list[dict]:
    """Get all enabled remote devices for dropdown selection"""
    from core.system.db import load_config
    remotes = load_config("remotes") or {}

    result = [{"id": "local", "label": "Lokal"}]
    for remote_id, remote in remotes.items():
        if remote.get("enabled"):
            result.append({
                "id": remote_id,
                "label": remote.get("host"),
                "host": remote.get("host"),
                "ssh_user": remote.get("ssh_user"),
                "ssh_port": remote.get("ssh_port", 22),
            })

    return result
