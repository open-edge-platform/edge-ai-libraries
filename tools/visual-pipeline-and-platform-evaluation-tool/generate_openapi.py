import json
from vippet.api.main import app

if __name__ == "__main__":
    schema = app.openapi()
    with open("api/vippet.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("OpenAPI schema written to vippet/api/vippet.json")
