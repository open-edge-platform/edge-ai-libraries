Update the mocked pytest suite to cover a newly onboarded VLM family without triggering a real model download.

- Add tests for the new model's dispatch branch and its model_config.yaml entry (pixel limits, video capability).
- Mock initialize_model — importing src/app.py loads the model at import time, so unmocked collection would download a multi-GB model.
- Keep the tests offline and CPU-only, matching the existing four-module suite. Add the SPDX header to any new test file.

Validate the change using:
- Run from where pytest.ini lives: cd tests && poetry run pytest
- Produce a coverage report: poetry run coverage run --source=src -m pytest && poetry run coverage report

Expected results:
- New tests pass with no model download; the new dispatch branch and config entry are covered.
- The full suite still runs fast and offline.
