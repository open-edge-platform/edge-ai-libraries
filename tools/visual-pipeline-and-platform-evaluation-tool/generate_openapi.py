import json
from vippet.api.main import app, register_routers

if __name__ == "__main__":
    # Register all routers without full initialization
    register_routers(app)

    schema = app.openapi()
    with open("../docs/user-guide/_assets/vippet.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("OpenAPI schema written to docs/user-guide/_assets/vippet.json")
