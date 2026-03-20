# BackupCtl – Remote Device SSH Unification Implementation

## Overview

Implement unified SSH-User management where Remote Devices become the single source of truth for all SSH configuration (host, user, port). Jobs select Remote Devices from dropdowns instead of typing hosts and users manually.

**Key Benefit:** SSH-User defined once per server, automatically used everywhere, fully backwards compatible.

---

## Problem (Current State)

- **Borg:** Has `ssh_user` field (only for hooks, backup itself hardcoded to backupadm)
- **Rsync:** No `ssh_user`, hardcoded to backupadm
- **Proxmox:** No `ssh_user`, hardcoded to backupadm
- **Remote Devices:** Has `ssh_user` (only used for WoL/shutdown)

→ SSH-User scattered, inconsistent, hard to maintain

## Solution

Make Remote Devices the single source of truth:
```
Remote Device (define once):
  ├─ id: 1
  ├─ description: "Server 1"
  ├─ host: "server1.lan"
  ├─ ssh_user: "backupadm"      ← Primary SSH user for backups
  ├─ ssh_port: 22
  ├─ mac: "aa:bb:cc:..."        ← For WoL
  └─ shutdown_user: "root"      ← For shutdown (optional)

All Jobs (reference only):
  ├─ Borg Job: source_remote_id: 1
  ├─ Rsync Job: source_remote_id: 1
  └─ Proxmox Job: remote_id: 1
  → All get host + ssh_user automatically
```

---

## Implementation Steps

### Step 1: Extend Remote Devices Schema

**File:** `core/modules/remotes/schema.yaml`

Replace entire contents with:
```yaml
modal_width: 800
id_field: id

fields:
  - name: description
    type: text
    label: Beschreibung
    max: 100
    column: 1
    row: 1

  - name: enabled
    type: boolean
    label: Aktiviert
    column: 2
    row: 1

  - name: host
    type: text
    label: Hostname / IP
    placeholder: "server.lan"
    max: 100
    column: 2
    row: 2

  - name: mac
    type: text
    label: MAC-Adresse (Wake-on-LAN)
    placeholder: "aa:bb:cc:dd:ee:ff"
    max: 17
    column: 1
    row: 2

  - type: section
    label: SSH-Authentifizierung (Backups)
    cols: 2

  - name: ssh_user
    type: text
    label: SSH-Benutzer
    placeholder: "backupadm"
    max: 50
    default: backupadm
    column: 1
    row: 3

  - name: ssh_port
    type: integer
    label: SSH-Port
    default: 22
    column: 2
    row: 3

  - type: section
    label: Optional: Shutdown
    cols: 1

  - name: shutdown_user
    type: text
    label: SSH-Benutzer (für Shutdown)
    placeholder: "root"
    max: 50
    default: root
```

**Migration:** Existing remotes with `ssh_user: "root"` will be read as backup user. Manually update ones that need `shutdown_user` different.

---

### Step 2: Create Remote Device Engine

**File:** `core/modules/remotes/engine.py` (CREATE NEW)

```python
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
    remote = get_remote(remote_id)
    if not remote:
        raise ValueError(f"Remote Device '{remote_id}' not found")
    
    if not remote.get("enabled"):
        raise ValueError(f"Remote Device '{remote_id}' is disabled")
    
    host = remote.get("host")
    if not host:
        raise ValueError(f"Remote Device '{remote_id}': No host configured")
    
    ssh_user = remote.get("ssh_user") or "backupadm"
    ssh_port = int(remote.get("ssh_port", 22))
    
    return (host, ssh_user, ssh_port)


def get_all_remotes_for_select() -> list[dict]:
    """Get all enabled remote devices for dropdown selection"""
    from core.system.db import load_config
    remotes = load_config("remotes") or {}
    
    result = []
    for remote_id, remote in remotes.items():
        if remote.get("enabled"):
            result.append({
                "id": remote_id,
                "label": f"{remote.get('description')} ({remote.get('host')})",
                "host": remote.get("host"),
                "ssh_user": remote.get("ssh_user", "backupadm"),
                "ssh_port": remote.get("ssh_port", 22),
            })
    
    return sorted(result, key=lambda x: x["label"])
```

---

### Step 3: Add API Endpoint

**File:** `core/modules/remotes/api.py`

Add this endpoint (append to existing code):
```python
@router.get("/api/remotes/for-select")
def remotes_for_select():
    """Returns all enabled remotes for job form dropdowns"""
    from .engine import get_all_remotes_for_select
    return {"options": get_all_remotes_for_select()}
```

---

### Step 4: Update Job Schemas

For **each** of these files, replace the source/target host fields:

- `app/modules/borg/schema.yaml`
- `app/modules/rsync/schema.yaml`
- `app/modules/proxmox_jobs/schema.yaml`
- `app/modules/proxmox_lxc/schema.yaml`
- `app/modules/proxmox_hosts/schema.yaml`

**Pattern for Borg/Rsync (has source + target):**

Replace the "Quelle" and "Ziel" sections with:
```yaml
  - type: section
    label: Quelle
    cols: 2

  - name: source_remote_id
    type: select
    label: Source Server
    options_endpoint: /api/remotes/for-select
    required: true

  - name: source_path
    type: text
    label: Source Path
    max: 200

  - type: section
    label: Ziel
    cols: 2

  - name: target_remote_id
    type: select
    label: Target Server
    options_endpoint: /api/remotes/for-select
    required: false

  - name: target_path
    type: text
    label: Target Path
    max: 200
```

Keep hidden for backwards compatibility at end of file:
```yaml
  - name: source_host
    type: hidden
  - name: target_host
    type: hidden
  - name: ssh_user
    type: hidden
```

**Pattern for Proxmox modules (single host):**

Replace host section:
```yaml
  - name: remote_id
    type: select
    label: Proxmox Host
    options_endpoint: /api/remotes/for-select
    required: true

  - name: host
    type: hidden
```

---

### Step 5: Add Helper Function to Each Job Module

**Add to each:** `app/modules/borg/jobs.py`, `app/modules/rsync/jobs.py`, etc.

```python
def _get_host_info(entry: dict, host_type: str = "source") -> tuple[str, str, int]:
    """
    Resolve host/ssh_user/ssh_port from Remote Device OR legacy fields.
    
    Tries:
    1. New way: {host_type}_remote_id → Remote Device
    2. Old way: {host_type}_host + ssh_user fields
    """
    remote_id_key = f"{host_type}_remote_id"
    host_key = f"{host_type}_host"
    
    # NEW: Remote Device
    if remote_id_key in entry and entry[remote_id_key]:
        from core.modules.remotes.engine import get_remote_ssh
        try:
            return get_remote_ssh(entry[remote_id_key])
        except ValueError as e:
            log("ERROR", str(e))
            raise
    
    # OLD: Direct host (backwards compat)
    elif host_key in entry and entry[host_key]:
        host = entry[host_key]
        ssh_user = entry.get("ssh_user") or "backupadm"
        ssh_port = 22
        return (host, ssh_user, ssh_port)
    
    else:
        raise ValueError(
            f"Job missing: neither '{remote_id_key}' nor '{host_key}' configured"
        )
```

For Proxmox, use `host_type="remote"`:
```python
def _get_proxmox_host_info(entry: dict) -> tuple[str, str, int]:
    """Get proxmox host info from remote or legacy host field"""
    if "remote_id" in entry and entry["remote_id"]:
        from core.modules.remotes.engine import get_remote_ssh
        try:
            return get_remote_ssh(entry["remote_id"])
        except ValueError as e:
            log("ERROR", str(e))
            raise
    elif "host" in entry:
        return (entry["host"], "backupadm", 22)
    else:
        raise ValueError("Job missing: neither 'remote_id' nor 'host' configured")
```

---

### Step 6: Update Job Code to Use Helper

**In Borg `jobs.py` - `preview()` function:**

Find these lines:
```python
source_host = entry.get("source_host")
ssh_user = entry.get("ssh_user") or "backupadm"
connection = build_connection_string(source_host, ssh_user)
```

Replace with:
```python
try:
    source_host, ssh_user, ssh_port = _get_host_info(entry, "source")
except ValueError as e:
    return [{"label": "Error", "cmd": str(e)}]

connection = build_connection_string(source_host, ssh_user)
```

**Do same for:**
- `run_single()` function
- Any other place that reads `source_host` or `target_host`

**In Rsync `jobs.py`:**
Replace:
```python
connection = build_connection_string(source_host)
```

With:
```python
try:
    source_host, ssh_user, ssh_port = _get_host_info(entry, "source")
except ValueError as e:
    log("ERROR", str(e))
    return

connection = build_connection_string(source_host, ssh_user)
```

**In Proxmox modules - `run_single()` function:**

Replace:
```python
host = entry.get("host")
```

With:
```python
try:
    host, ssh_user, ssh_port = _get_proxmox_host_info(entry)
except ValueError as e:
    log("ERROR", str(e))
    return
```

---

### Step 7: Fix require_hosts() Calls

In `require_hosts()` calls (in `run_single()` functions), pass the ssh_user:

**Before:**
```python
if not require_hosts([source_host]):
    return
```

**After:**
```python
if not require_hosts([source_host], user=ssh_user):
    return
```

Do this for all job modules in their `run_single()` functions.

---

## Testing Checklist

- [ ] Create 2-3 Remote Devices with different ssh_users
- [ ] Open Borg job form → source/target dropdowns show remotes ✓
- [ ] Open Rsync job form → source/target dropdowns work ✓
- [ ] Open Proxmox job form → remote dropdown works ✓
- [ ] Create new job using Remote Device selection
- [ ] Preview shows correct `ssh_user@host` ✓
- [ ] Run job completes successfully ✓
- [ ] Open old job (with source_host) → still shows preview ✓
- [ ] require_hosts() passes correct ssh_user ✓
- [ ] Test with different ssh_users per server ✓

---

## Backwards Compatibility

- Old jobs with `source_host` + `ssh_user` fields continue working
- `_get_host_info()` helper automatically detects which format is used
- No data migration needed
- Users can gradually migrate old jobs or keep them as-is

---

## Files to Create
- `core/modules/remotes/engine.py` (NEW)

## Files to Modify
- `core/modules/remotes/schema.yaml`
- `core/modules/remotes/api.py` (add endpoint)
- `app/modules/borg/schema.yaml`
- `app/modules/borg/jobs.py` (add helper + update functions)
- `app/modules/rsync/schema.yaml`
- `app/modules/rsync/jobs.py` (add helper + update functions)
- `app/modules/proxmox_jobs/schema.yaml`
- `app/modules/proxmox_jobs/jobs.py` (add helper + update functions)
- `app/modules/proxmox_lxc/schema.yaml`
- `app/modules/proxmox_lxc/jobs.py` (add helper + update functions)
- `app/modules/proxmox_hosts/schema.yaml`
- `app/modules/proxmox_hosts/jobs.py` (add helper + update functions)

---

## Expected Outcome

✅ All job modules use Remote Device selection  
✅ SSH-User automatically resolved from Remote Device  
✅ Old jobs continue to work  
✅ Single source of truth for server SSH configuration  
✅ Future flexible (can change ssh_user per server anytime)