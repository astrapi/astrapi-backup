"""backupctl._cli – Console-Script-Einstiegspunkt.

Start:
    backupctl                   # Port 5001 (Standard)
    backupctl --port 9999
    backupctl --reload          # mit File-Watcher (nur Entwicklung)
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="backupctl")
    parser.add_argument("--port",   type=int, default=5001)
    parser.add_argument("--host",   default="0.0.0.0")
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "backupctl._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
