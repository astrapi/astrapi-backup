# modules/proxmox_lxc.py
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from astrapi_core.system.db import get_entry as _get_entry
from astrapi_core.system.db import load_config as _load_config
from astrapi_core.system.db import patch_item as _patch_item
from astrapi_core.system.logger import log, log_context
from astrapi_core.system.runner import worst_status as _worst
from astrapi_core.ui.settings_registry import get_module as _get_module_setting

KEY = "proxmox_lxc"


def _get_config():
    return _load_config(KEY)


def _verify_ssl(remote: dict) -> bool:
    return str(remote.get("api_verify_ssl", False)).lower() in ("1", "true", "on", "yes")


def _api_token(remote: dict) -> tuple[str, str]:
    token_id = remote.get("api_token_id", "").strip()
    token_secret = remote.get("api_token_secret", "").strip()
    if not token_id or not token_secret:
        raise ValueError(f"API-Token für Remote '{remote.get('host')}' nicht konfiguriert")
    return token_id, token_secret


def _cluster_vm_map() -> tuple[dict, dict, dict]:
    """Fragt /cluster/resources EINMAL ab.

    Gibt (vmid → node_name, node_name → remote, cluster_remote) zurück.
    Eine Abfrage liefert alle Container; vorher lief sie einmal pro VMID.
    """
    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select, get_remote

    # Alle proxmox_node-Remotes mit vollständigen Daten laden
    node_remotes = {}  # short_name → remote_obj
    for r in get_all_remotes_for_select(type_filter="proxmox_node"):
        if not r.get("host"):
            continue
        remote_obj = get_remote(str(r["id"])) or {}
        short = r["host"].split(".")[0]
        node_remotes[short] = remote_obj

    if not node_remotes:
        raise ValueError("Keine Proxmox-Node-Remotes konfiguriert")

    # Ersten Remote mit Token für Cluster-Abfrage verwenden
    cluster_remote = next((r for r in node_remotes.values() if r.get("api_token_id")), None)
    if not cluster_remote:
        raise ValueError("Kein Proxmox-Node-Remote mit API-Token konfiguriert")

    token_id, token_secret = _api_token(cluster_remote)
    verify_ssl = _verify_ssl(cluster_remote)
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    first_host = cluster_remote["host"]
    headers = _auth_headers(token_id, token_secret)
    url = f"https://{first_host}:8006/api2/json/cluster/resources?type=vm"

    from astrapi_core.system.paths import is_debug

    if is_debug():
        log("INFO", f"curl -sk -H 'Authorization: PVEAPIToken={token_id}:<secret>' '{url}'")
    resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
    resp.raise_for_status()

    vm_nodes = {}
    for r in resp.json().get("data", []):
        try:
            vm_nodes[int(r.get("vmid", 0))] = r["node"]
        except (TypeError, ValueError, KeyError):
            continue
    return vm_nodes, node_remotes, cluster_remote


def _node_target(node_name: str, node_remotes: dict, cluster_remote: dict) -> tuple[str, dict]:
    remote = node_remotes.get(node_name, cluster_remote)
    return remote.get("host", cluster_remote.get("host", "")), remote


def _resolve_node_for_vmid(vmid: int) -> tuple[str, str, dict]:
    """Ermittelt via Cluster-API welcher Node den Container hat.
    Gibt (host, node_name, remote) zurück.
    """
    vm_nodes, node_remotes, cluster_remote = _cluster_vm_map()
    node_name = vm_nodes.get(vmid)
    if node_name is None:
        raise ValueError(f"VMID {vmid} nicht im Cluster gefunden")
    host, remote = _node_target(node_name, node_remotes, cluster_remote)
    return host, node_name, remote


def _auth_headers(token_id: str, token_secret: str) -> dict:
    return {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}


def _trigger_vzdump(host: str, node_name: str, vmid: int, remote: dict) -> str:
    """Startet vzdump via Proxmox API. Gibt den UPID des Tasks zurück."""
    token_id, token_secret = _api_token(remote)
    verify_ssl = _verify_ssl(remote)
    storage = _get_module_setting(KEY, "backup_storage", "backup01")
    mode = _get_module_setting(KEY, "backup_mode", "snapshot")
    notes_template = _get_module_setting(KEY, "notes_template", "{{guestname}}")

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = f"https://{host}:8006/api2/json/nodes/{node_name}/vzdump"
    data = {
        "vmid": str(vmid),
        "storage": storage,
        "mode": mode,
        "notes-template": notes_template,
    }
    resp = requests.post(
        url, headers=_auth_headers(token_id, token_secret), data=data, verify=verify_ssl, timeout=30
    )
    resp.raise_for_status()
    upid = resp.json().get("data", "")
    if not upid:
        raise ValueError("vzdump API: kein UPID in der Antwort")
    return upid


def _wait_for_task(
    host: str, node_name: str, upid: str, remote: dict, poll_interval: int = 5, timeout: int = 3600
) -> str:
    """Pollt den Task-Status bis er abgeschlossen ist. Gibt exitstatus zurück."""
    token_id, token_secret = _api_token(remote)
    verify_ssl = _verify_ssl(remote)
    headers = _auth_headers(token_id, token_secret)

    upid_enc = urllib.parse.quote(upid, safe="")
    url = f"https://{host}:8006/api2/json/nodes/{node_name}/tasks/{upid_enc}/status"

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "")
        if status == "stopped":
            return data.get("exitstatus", "unknown")
        time.sleep(poll_interval)
    raise TimeoutError(f"Task {upid} nicht innerhalb von {timeout}s abgeschlossen")


def preview(item_id) -> list[dict]:
    """Gibt den API-Aufruf zurück, der bei run_single ausgeführt würde."""
    entry = _get_entry(_get_config(), item_id)
    if entry is None:
        return []

    vmid = entry.get("vmid")
    if vmid is None:
        return []

    try:
        host, node_name, remote = _resolve_node_for_vmid(int(vmid))
    except Exception as e:
        return [{"label": "Error", "cmd": str(e)}]

    storage = _get_module_setting(KEY, "backup_storage", "backup01")
    mode = _get_module_setting(KEY, "backup_mode", "snapshot")
    token_id = remote.get("api_token_id", "").strip() or "<api-token-id>"

    url = f"https://{host}:8006/api2/json/nodes/{node_name}/vzdump"
    cmd = (
        f"curl -k -X POST "
        f"-H 'Authorization: PVEAPIToken={token_id}=<secret>' "
        f"'{url}' "
        f"-d 'vmid={vmid}' -d 'storage={storage}' -d 'mode={mode}'"
    )
    return [{"label": "vzdump (API)", "cmd": cmd}]


def run() -> str:
    config = _get_config()
    jobs = [
        {"item_id": item_id, "vmid": int(e["vmid"]), "name": e.get("description", item_id)}
        for item_id, e in config.items()
        if e.get("enabled") and e.get("vmid") is not None
    ]
    if not jobs:
        return "ok"

    # Ganze Liste vorab als eingeplant markieren – anders als bei run_all()
    # (borg etc.) geht dieser Pfad nicht ueber dessen mark_pending_fn, weil
    # run() hier komplett eigenstaendig ist (Cluster-Aufloesung + Node-Pools).
    for j in jobs:
        _patch_item(KEY, j["item_id"], last_status="pending")

    # Ohne max_workers nimmt Python cpu_count()+4 – auf einem Vierkerner also
    # acht gleichzeitige vzdump-Auftraege. Das Limit gilt PRO NODE: verschiedene
    # Nodes arbeiten unabhaengig voneinander, nur derselbe Node wird gedrosselt.
    try:
        pro_node = max(1, int(_get_module_setting(KEY, "max_parallel", 2)))
    except (TypeError, ValueError):
        pro_node = 2

    # Einmal aufloesen statt einmal pro VMID – und noetig, um vor dem Start
    # nach Node gruppieren zu koennen.
    try:
        vm_nodes, node_remotes, cluster_remote = _cluster_vm_map()
    except Exception as e:
        log("ERROR", f"Cluster-Abfrage fehlgeschlagen: {e}")
        for j in jobs:
            _patch_item(KEY, j["item_id"], last_status="error")
        return "error"

    overall = "ok"
    nach_node: dict = {}
    for j in jobs:
        node = vm_nodes.get(j["vmid"])
        if node is None:
            log("ERROR", f"LXC '{j['name']}': VMID {j['vmid']} nicht im Cluster gefunden")
            _patch_item(KEY, j["item_id"], last_status="error")
            overall = _worst(overall, "error")
            continue
        j["host"], j["remote"] = _node_target(node, node_remotes, cluster_remote)
        j["node"] = node
        # Node-Spalte in der Liste fuellen. Das Schema fuehrt "node" als
        # info-Feld mit resolve: remote_host, es wurde aber nie geschrieben --
        # die Spalte zeigte deshalb fuer jeden Eintrag "Lokal". Gespeichert
        # wird die Remote-ID, denn resolve_remote_host() erwartet diese.
        remote_id = str(j["remote"].get("id", "")) if j["remote"] else ""
        if remote_id:
            _patch_item(KEY, j["item_id"], node=remote_id)
        nach_node.setdefault(node, []).append(j)

    if not nach_node:
        return overall

    log(
        "INFO",
        f"LXC: {sum(len(v) for v in nach_node.values())} Eintrag/Eintraege auf "
        f"{len(nach_node)} Node(s), max. {pro_node} je Node",
    )

    def _node_abarbeiten(node: str, node_jobs: list) -> str:
        """Arbeitet die Eintraege EINES Nodes mit hoechstens pro_node Threads ab.
        Gibt den schlechtesten Status ueber alle Eintraege dieses Nodes zurueck (T-056)."""
        node_status = "ok"
        with ThreadPoolExecutor(max_workers=pro_node) as pool:
            futures = {
                pool.submit(_run_single_job, j["item_id"], j["vmid"], j["name"],
                            j["host"], j["node"], j["remote"]): j["name"]
                for j in node_jobs
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    node_status = _worst(node_status, future.result())
                except Exception as e:
                    log("ERROR", f"LXC '{name}': {e}")
                    node_status = _worst(node_status, "error")
        return node_status

    # Ein Thread je Node, der seinen eigenen begrenzten Pool fuehrt.
    with ThreadPoolExecutor(max_workers=len(nach_node)) as nodes:
        node_futures = {
            nodes.submit(_node_abarbeiten, node, node_jobs): node
            for node, node_jobs in nach_node.items()
        }
        for future in as_completed(node_futures):
            node = node_futures[future]
            try:
                overall = _worst(overall, future.result())
            except Exception as e:
                log("ERROR", f"Node '{node}': {e}")
                overall = _worst(overall, "error")

    return overall


def check_availability() -> str:
    """Prüft nur, ob die konfigurierten VMIDs noch im Proxmox-Cluster
    existieren -- löst dabei KEIN Backup aus (anders als run()). Setzt
    last_status je Eintrag, damit sich das Ergebnis in der bestehenden
    Status-Spalte zeigt statt eine eigene UI zu brauchen: "warning" wenn
    die VMID nicht mehr im Cluster gefunden wurde (bewusst nicht "error" --
    das würde sich mit echten Backup-Fehlern vermischen), "error" nur wenn
    die Cluster-Abfrage selbst fehlschlägt (Netzwerk/Auth).
    """
    config = _get_config()
    entries = [
        {"item_id": item_id, "vmid": int(e["vmid"])}
        for item_id, e in config.items()
        if e.get("vmid") is not None
    ]
    if not entries:
        return "ok"

    try:
        vm_nodes, node_remotes, cluster_remote = _cluster_vm_map()
    except Exception as e:
        log("ERROR", f"Verfügbarkeitsprüfung: Cluster-Abfrage fehlgeschlagen: {e}")
        for entry in entries:
            _patch_item(KEY, entry["item_id"], last_status="error")
        return "error"

    overall = "ok"
    for entry in entries:
        node = vm_nodes.get(entry["vmid"])
        if node is None:
            log("WARNING", f"Verfügbarkeitsprüfung: VMID {entry['vmid']} nicht im Cluster gefunden")
            _patch_item(KEY, entry["item_id"], last_status="warning")
            overall = _worst(overall, "warning")
            continue
        _, remote = _node_target(node, node_remotes, cluster_remote)
        remote_id = str(remote.get("id", "")) if remote else ""
        updates = {"last_status": "ok"}
        if remote_id:
            updates["node"] = remote_id
        _patch_item(KEY, entry["item_id"], **updates)

    return overall


def run_single(item_id, entry=None):
    entry = _get_entry(_get_config(), item_id)
    if not entry:
        log("ERROR", f"LXC-Eintrag '{item_id}' nicht gefunden")
        return
    with log_context(KEY, item_id):
        vmid = entry.get("vmid")
        if vmid is None:
            log("ERROR", f"LXC-Eintrag '{item_id}': Pflichtfeld vmid fehlt")
            return
        name = entry.get("description", item_id)
        _patch_item(KEY, item_id, last_status="running")
        log("INFO", f"=== LXC '{name}' gestartet ===")
        status = _backup_lxc(int(vmid), name)
        from datetime import datetime

        _patch_item(
            KEY, item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"), last_status=status
        )
        log("INFO", f"=== LXC '{name}' abgeschlossen ===")


def _run_single_job(item_id, vmid: int, name: str, host=None, node=None, remote=None):
    from datetime import datetime

    from astrapi_core.system.runner import run_logged

    # Auch im parallelen Pfad als laufend markieren. run() geht nicht ueber
    # run_single(), deshalb fehlte der Spinner hier – anders als bei borg,
    # das ueber run_all(..., run_single) laeuft.
    _patch_item(KEY, item_id, last_status="running")
    ziel = (host, node, remote) if node else None

    def _mit_rahmen(v=vmid, n=name, z=ziel):
        # Dieselben Rahmenzeilen wie run_single(). Ohne sie sieht derselbe
        # Vorgang im Log unterschiedlich aus, je nachdem ob er von Hand oder
        # vom Scheduler ausgeloest wurde – das macht jede Suche unnoetig schwer.
        log("INFO", f"=== LXC '{n}' gestartet ===")
        try:
            return _backup_lxc(v, n, z)
        finally:
            log("INFO", f"=== LXC '{n}' abgeschlossen ===")

    status = run_logged(KEY, str(item_id), name, _mit_rahmen)
    _patch_item(KEY, item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"), last_status=status)
    return status


def _backup_lxc(vmid: int, name: str, ziel: tuple | None = None) -> str:
    """ziel: (host, node_name, remote) falls bereits aufgeloest – run() gibt es
    gebuendelt mit, run_single() loest einzeln auf."""
    try:
        host, node_name, remote = ziel if ziel else _resolve_node_for_vmid(vmid)
        log("INFO", f"LXC '{name}': Node {node_name} ({host})")
        upid = _trigger_vzdump(host, node_name, vmid, remote)
        log("INFO", f"LXC '{name}': Task gestartet ({upid})")
        exitstatus = _wait_for_task(host, node_name, upid, remote)
        from astrapi_backup.api.proxmox import log_level, task_status

        status = task_status(exitstatus)
        if status == "ok":
            log("INFO", f"LXC '{name}' erfolgreich")
        else:
            log(
                log_level(status),
                f"LXC '{name}' abgeschlossen mit Status: {exitstatus}",
            )
        return status
    except Exception as e:
        log("WARNING", f"LXC '{name}' fehlgeschlagen")
        log("ERROR", str(e))
        return "error"
