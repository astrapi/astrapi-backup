#main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware
from ui.app import create as create_ui
from api.app import create as create_api
import uvicorn


def create_app():
    
    api = create_api()
    ui = create_ui()

    app = api

    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.mount("/api", api)
    app.mount("/", WSGIMiddleware(ui))

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9999, reload=True)
