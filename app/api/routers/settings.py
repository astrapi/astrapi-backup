# api/routers/settings.py
#
# Alle Endpunkte wurden in die jeweiligen Module migriert:
#
#   Scheduler  → core/modules/scheduler  (eigenes Modul mit vollem Job-System)
#   ntfy       → core/modules/notify     (Kanal-/Job-CRUD in eigenem Modul)
#   WoL        → /api/wol/settings       (app/modules/wol)
#   Repos-Pfad → /api/repos/settings/base-path  (app/modules/repos)
#   Borg-PW    → /api/repos/settings/passphrase (app/modules/repos)
#   PBS-Secrets→ /api/proxmox_hosts/settings/secrets (app/modules/proxmox_hosts)