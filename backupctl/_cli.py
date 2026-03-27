"""backupctl._cli – Console-Script-Einstiegspunkt.

Start:
    backupctl --work-dir /opt/backupctl --port 9999
    backupctl --work-dir /opt/backupctl --port 9998 --reload   # Entwicklung
"""
import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="backupctl")
    parser.add_argument("--port",     type=int, default=5001)
    parser.add_argument("--host",     default="0.0.0.0")
    parser.add_argument("--reload",   action="store_true", default=False)
    parser.add_argument("--work-dir", required=True,
                        help="Arbeitsverzeichnis mit data/ und logs/")
    args = parser.parse_args()

    os.environ["BACKUPCTL_WORK_DIR"] = args.work_dir

    import uvicorn
    uvicorn.run(
        "backupctl._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
