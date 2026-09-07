"""Export the backend contract for frontend type generation."""

import json
from pathlib import Path

from pcb_inspector.api import create_app
from pcb_inspector.config import Settings

destination = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
app = create_app(Settings(_env_file=None, environment="test", database_url="sqlite:///:memory:"))
try:
    destination.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
finally:
    app.state.repository.engine.dispose()
