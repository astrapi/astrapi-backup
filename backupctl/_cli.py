"""backupctl._cli – Console-Script-Einstiegspunkt.

Start:
    backupctl                               # Port 5001, Daten in ./data/
    backupctl --port 9999 --data-dir /opt/backupctl
    backupctl --reload                      # mit File-Watcher (nur Entwicklung)
"""
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="backupctl")
    parser.add_argument("--port",     type=int, default=5001)
    parser.add_argument("--host",     default="0.0.0.0")
    parser.add_argument("--reload",   action="store_true", default=False)
    parser.add_argument("--data-dir", default=None,
                        help="Verzeichnis für data/ und logs/ (Standard: cwd)")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["BACKUPCTL_DATA_DIR"] = args.data_dir

    import uvicorn
    uvicorn.run(
        "backupctl._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
