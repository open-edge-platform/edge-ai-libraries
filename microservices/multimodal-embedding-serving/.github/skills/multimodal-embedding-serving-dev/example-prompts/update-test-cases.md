Update the test suite so a newly onboarded embedding model family is covered and future changes can't silently break it.

- Add or extend tests that exercise the new handler's encode_text and (if multimodal) encode_image.
- Assert a batch of N inputs returns N equal-length vectors (locks in the OpenVINO fixed-batch pad/split path).
- Keep the tests offline and CPU-only, matching the existing suite's style. Add the SPDX header to any new test file.

Validate the change using:
- The newly onboarded family (a small variant).
- A batch of 3 text inputs in one POST /embeddings call.
- Run: poetry run python -m unittest from the microservice root.

Expected results:
- New tests pass: text (and image, if supported) return correctly shaped vectors; 3 inputs yield 3 equal-length vectors.
- The full existing suite still passes.
