import json
from vippet.api.main import app

if __name__ == "__main__":
    schema = app.openapi()
    with open("../docs/user-guide/_assets/vippet.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("OpenAPI schema written to docs/user-guide/_assets/vippet.json")
