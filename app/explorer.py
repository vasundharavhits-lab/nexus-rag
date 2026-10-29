# app/explorer.py
from pathlib import Path
from fastapi.responses import FileResponse

PAGE = Path(__file__).parent / "static" / "explorer.html"

def register(app):
    @app.get("/explorer", include_in_schema=False)
    def explorer():
        return FileResponse(PAGE)
