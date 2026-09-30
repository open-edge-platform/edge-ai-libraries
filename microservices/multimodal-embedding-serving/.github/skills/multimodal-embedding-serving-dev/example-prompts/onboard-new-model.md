Onboard a new image+text embedding model family into this service so it is selectable over both the REST API and the SDK.

- Add a handler under src/models/handlers/ implementing load_model, encode_text, and encode_image (PyTorch path; optional OpenVINO path).
- Register the family in src/models/registry.py and add its model ids (Family/name form) to the registry in src/models/config.py.
- Keep the new module importable under the packaged name so SDK users (multimodal_embedding_serving) get it too.
- Do not change src/wrapper.py's public API — it is a path dependency of multimodal-dataprep. Add the SPDX header to any new file.

Validate the change using:
- Select the new model via EMBEDDING_MODEL_NAME and confirm it appears in GET /models on http://localhost:9777.
- Embed one text and one image against the new model.
- Run: poetry run python -m unittest tests/test_path_security.py -v

Expected results:
- The new family loads, appears in GET /models, and returns one flat vector for text and one for image.
- The existing test suite still passes and src/wrapper.py's signatures are unchanged.
