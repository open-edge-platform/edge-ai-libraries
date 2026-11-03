# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The database endpoints, and the example payloads `scripts/` posts to them.

`tests/test_databases.py` covers the registry itself. What lives only in
`api/databases.py` is the part that decides *answers*: which HTTP status a
failure deserves, who is using a database, and whether a credential leaves the
process. None of that was exercised by anything until now -- the compose
bootstrap was the only thing that ever called these routes, which is not a test.

The second half checks the checked-in example payloads against the schemas they
are posted to. It is a small test that would have caught a real bug: the
database schema was renamed `database_id`/`database_type` to `id`/`type`, and
the bootstrap kept sending the old names, which no unit test could see because
the payload lived in a YAML string.
"""

import ast
import asyncio
import json
import os
import sys
import types

import pytest

from databasehub.manager import REDACTED, DatabaseHubManager
from . import dbhub

# --- stubs ---------------------------------------------------------------------
#
# `api/databases.py` imports fastapi and the pydantic schemas, neither of which
# the unit environment has. The routes are plain async functions underneath, so
# standing in for the decorators is enough to call them directly -- which also
# keeps these tests about the logic rather than about HTTP.


def _install_stubs() -> None:
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code, detail=""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class APIRouter:
            def __init__(self, **kwargs):
                self.routes = []

            def _register(self, *args, **kwargs):
                def decorate(function):
                    self.routes.append(function)
                    return function

                return decorate

            get = post = patch = delete = put = _register

        fastapi.APIRouter = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.status = types.SimpleNamespace(
            HTTP_201_CREATED=201,
            HTTP_204_NO_CONTENT=204,
            HTTP_400_BAD_REQUEST=400,
            HTTP_404_NOT_FOUND=404,
            HTTP_409_CONFLICT=409,
            HTTP_503_SERVICE_UNAVAILABLE=503,
        )
        sys.modules["fastapi"] = fastapi

    # The harness may stub `schemas` with a permissive namespace; the
    # database models are not among the names it knows about.
    schemas = sys.modules.get("schemas")
    if schemas is not None:
        for name in (
            "BackendOption",
            "DatabaseCheck",
            "DatabaseIn",
            "DatabaseOut",
            "DatabaseUpdate",
        ):
            if not hasattr(schemas, name):
                setattr(
                    schemas,
                    name,
                    type(
                        name,
                        (),
                        {"__init__": lambda self, **kw: self.__dict__.update(kw)},
                    ),
                )


_install_stubs()

from api import databases as api  # noqa: E402 - needs the stubs above

HTTPException = sys.modules["fastapi"].HTTPException

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def run(coroutine):
    return asyncio.run(coroutine)


class FakeLibrary:
    def __init__(self, name, sources=(), default_content_source_id=""):
        self.name = name
        self.sources = {
            source.source_id: source for source in sources
        }
        self.default_content_source_id = default_content_source_id


class FakeSource:
    def __init__(self, source_id, name, database_id):
        self.source_id = source_id
        self.name = name
        self.database_id = database_id


class FakeRegistry:
    def __init__(self, libraries=()):
        self._libraries = list(libraries)

    def list(self):
        return self._libraries


def setup(hub=None, libraries=()):
    """Point the module at a throwaway hub and registry, and stub the save."""
    api.database_manager = hub if hub is not None else DatabaseHubManager()
    api.registry = FakeRegistry(libraries)
    api.database_repository = types.SimpleNamespace(save=lambda manager: True)
    return api.database_manager


# --- listing and reading --------------------------------------------------------


def test_an_engine_with_nothing_registered_lists_nothing():
    setup()

    assert run(api.list_databases()) == []


def test_backends_lists_every_registrable_pair():
    """Derived from `BACKENDS`, so adding a backend needs no second list.

    Note this reports what may be *registered*, not what works: `nebula` and
    `postgres` are placeholders that raise on every call. `check` is what
    distinguishes them -- see the ping tests below.
    """
    setup()

    by_type = {item.database_type: item for item in run(api.list_backends())}

    assert by_type["vector"].backends == ["milvus"]
    assert by_type["object"].backends == ["filesystem", "minio"]
    assert "nebula" in by_type["graph"].backends


def test_reading_one_that_is_not_registered_is_a_404():
    setup()

    with pytest.raises(HTTPException) as caught:
        run(api.get_database("nope"))
    assert caught.value.status_code == 404


# --- registering ----------------------------------------------------------------


def _database_in(**kw):
    body = {
        "id": "prod",
        "type": "vector",
        "backend": "milvus",
        "options": {"uri": "http://milvus:19530"},
        "description": "",
    }
    body.update(kw)
    return types.SimpleNamespace(**body)


def test_registering_returns_the_registration():
    setup()

    out = run(api.register_database(_database_in()))

    assert (out.id, out.type, out.backend) == ("prod", "vector", "milvus")
    assert out.in_use_by == []


def test_a_duplicate_is_a_409_and_a_bad_backend_is_a_400():
    setup()
    run(api.register_database(_database_in()))

    with pytest.raises(HTTPException) as caught:
        run(api.register_database(_database_in()))
    assert caught.value.status_code == 409

    with pytest.raises(HTTPException) as caught:
        run(api.register_database(_database_in(id="other", backend="pinecone")))
    assert caught.value.status_code == 400


def test_updating_one_that_is_not_registered_is_a_404_not_a_400():
    setup()

    with pytest.raises(HTTPException) as caught:
        run(
            api.update_database(
                "nope", types.SimpleNamespace(backend=None, options=None, description="x")
            )
        )
    assert caught.value.status_code == 404


# --- credentials -----------------------------------------------------------------


def test_a_credential_never_leaves_the_process():
    hub = setup()
    run(
        api.register_database(
            _database_in(
                id="store",
                type="object",
                backend="minio",
                options={"endpoint": "minio:9000", "secret_key": "hunter2"},
            )
        )
    )

    out = run(api.get_database("store"))

    assert out.options["secret_key"] == REDACTED
    assert out.options["endpoint"] == "minio:9000", "only the secret is masked"
    assert hub.require("store").options["secret_key"] == "hunter2", "but it is kept"


# --- who is using it --------------------------------------------------------------


def test_a_source_makes_a_database_in_use():
    hub = dbhub.object_hub("content")
    setup(
        hub,
        libraries=[
            FakeLibrary("docs", sources=[FakeSource("s1", "primary", "content")])
        ],
    )

    out = run(api.get_database("content"))

    assert out.in_use_by == ["docs/sources/primary"]


def _library_storing_content_in(database_id, name="docs"):
    """A library whose default content source points at `database_id`.

    Content is not a separate kind of user any more -- it is a source like the
    one above, and the default earns a clearer label. It used to be found
    through a field beside the sources, which missed a content source registered
    any other way.
    """
    source = FakeSource("c1", "content", database_id)
    return FakeLibrary(name, sources=[source], default_content_source_id="c1")


def test_the_default_content_source_is_reported_as_content():
    hub = dbhub.object_hub("content")
    setup(hub, libraries=[_library_storing_content_in("content")])

    out = run(api.get_database("content"))

    assert out.in_use_by == ["docs (content)"]


def test_a_content_source_that_is_not_the_default_is_reported_as_a_source():
    """A library may keep content in several stores; only one is the default."""
    hub = dbhub.object_hub("cold")
    setup(
        hub,
        libraries=[
            FakeLibrary(
                "docs",
                sources=[FakeSource("c2", "cold", "cold")],
                default_content_source_id="c1",
            )
        ],
    )

    out = run(api.get_database("cold"))

    assert out.in_use_by == ["docs/sources/cold"]


def test_deleting_one_in_use_is_refused_and_says_by_what():
    hub = dbhub.object_hub("content")
    setup(hub, libraries=[_library_storing_content_in("content")])

    with pytest.raises(HTTPException) as caught:
        run(api.remove_database("content"))

    assert caught.value.status_code == 409
    assert "docs (content)" in caught.value.detail
    assert hub.get("content") is not None, "and it is still registered"


def test_deleting_an_unused_one_works():
    hub = dbhub.object_hub("content")
    setup(hub, libraries=[FakeLibrary("docs")])

    run(api.remove_database("content"))

    assert hub.get("content") is None


def test_deleting_one_that_was_never_registered_is_a_404():
    setup()

    with pytest.raises(HTTPException) as caught:
        run(api.remove_database("nope"))
    assert caught.value.status_code == 404


# --- checking ---------------------------------------------------------------------


def test_an_unreachable_database_is_a_200_saying_so_not_an_error():
    """"Is it reachable" has an answer; failing to reach it is not a failure to
    answer."""
    hub = setup()
    hub.register("graph", database_type="graph", backend="nebula", options={})

    result = run(api.check_database("graph"))

    assert result.reachable is False
    assert result.error, "the reason travels with the answer"


def test_a_reachable_database_reports_no_error():
    hub = dbhub.object_hub("content")
    setup(hub)

    result = run(api.check_database("content"))

    assert (result.reachable, result.error) == (True, None)


def test_checking_one_that_is_not_registered_is_a_404():
    setup()

    with pytest.raises(HTTPException) as caught:
        run(api.check_database("nope"))
    assert caught.value.status_code == 404


# --- the example payloads scripts/ posts ------------------------------------------
#
# Read the schema's field names out of the source with `ast` rather than
# importing it: pydantic is not installed here, and the question is only "does
# this JSON name fields this model has".


def _schema_fields(class_name: str):
    source = open(
        os.path.join(os.path.dirname(SCRIPTS), "src", "schemas.py"),
        encoding="utf-8",
    ).read()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            required, optional = set(), set()
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign):
                    continue
                name = statement.target.id
                (optional if statement.value is not None else required).add(name)
            return required, optional
    raise AssertionError(f"no schema class named {class_name}")


def _example(name: str):
    with open(os.path.join(SCRIPTS, "example", name), encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize(
    "example,schema",
    [
        ("database.json", "DatabaseIn"),
        ("content-database.json", "DatabaseIn"),
        ("library.json", "AssetLibraryIn"),
        ("source.json", "SourceIn"),
        ("pool.json", "AssetPoolIn"),
        ("assets.json", "AssetCreateRequest"),
    ],
)
def test_an_example_payload_matches_the_schema_it_is_posted_to(example, schema):
    required, optional = _schema_fields(schema)
    keys = set(_example(example))

    unknown = keys - (required | optional)
    assert not unknown, f"{example} sends fields {schema} does not have: {unknown}"
    missing = required - keys
    assert not missing, f"{example} omits required {schema} fields: {missing}"


def test_the_two_database_examples_are_the_pair_the_stack_needs():
    """A vector database to index into and an object store for content: with
    neither, an engine cannot create a source or ingest a file."""
    kinds = {_example(name)["type"] for name in ("database.json", "content-database.json")}

    assert kinds == {"vector", "object"}


def test_the_content_example_roots_itself_inside_the_workspace():
    """Outside it, content is lost when the container is replaced while the
    library records referencing it survive."""
    root = _example("content-database.json")["options"]["root"]

    assert root.startswith("/workspace/")


def test_every_example_is_registrable_or_useful_json():
    """Catches a file that was edited into invalid JSON, which `databases.sh`
    would only report as a confusing 422."""
    directory = os.path.join(SCRIPTS, "example")
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            assert isinstance(_example(name), dict), name
