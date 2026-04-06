"""astrapi_backup._cli – Console-Script-Einstiegspunkt.

Start:
    astrapi-backup --work-dir /opt/astrapi-backup --port 5001
    astrapi-backup --work-dir /opt/astrapi-backup --port 5001 --debug    # Debug-Modus (inkl. reload)
"""
from astrapi.core.system.paths import run_app


def main() -> None:
    run_app("astrapi_backup._app:app", "astrapi-backup", default_port=5001)


if __name__ == "__main__":
    main()
