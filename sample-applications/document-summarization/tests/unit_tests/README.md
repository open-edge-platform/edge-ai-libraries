# Running Tests for Document Summarization App

This guide will help you run the tests for the Document Summarization App project using the pytest framework.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Running Tests in a Virtual Environment [RECOMMENDED]](#running-tests-in-a-virtual-environment-recommended)

---

## Prerequisites

Before running the tests, ensure you have the following installed:

- Python 3.11+
- `pip` (Python package installer)
- `Poetry` (Python dependency management and packaging tool)

You can install Poetry using the following command:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

---

## Running Tests in a Virtual Environment [RECOMMENDED]

If you prefer to run the tests in a virtual environment, please follow these steps:

1. **Clone the Repository**

   Clone the repository to your local machine:

   ```bash
   git clone <repository-url>
   cd ~/<repository-url>/sample-applications/document-summarization
   ```

2. **Setup the Environment Variables**

   Setup the environment variables:

   ```bash
    export VOLUME_OVMS==<model-export-path-for-OVMS>  # For example, use: export VOLUME_OVMS="$PWD"
    export LLM_MODEL=microsoft/Phi-3.5-mini-instruct
    export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
    export OTLP_ENDPOINT=<your-OTLP-endpoint> # Optional: Only if applicable
   ```

3. **Run Setup Script**

    Running setup.sh will install, create and activate virtualenv:

    ```bash
    source setup.sh
    ```

4. **Install Dependencies with Poetry**
    
    Install application dependencies packages using Poetry in the virtualenv created by setup.sh

    ```bash
    poetry install --with dev
    ```
5. **Navigate to the Tests Directory**

   Change to the directory containing the tests:

   ```bash
   cd edge-ai-libraries/sample-applications/document-summarization/tests/unit_tests
   ```

6. **Run the Tests**

   Use the below command to run the tests:

   ```bash
   poetry run pytest
   ```
   This will discover and run all the test cases defined in the `tests` directory.

7. **Deactivate Virtual Environment**

   Remember to deactivate the virtual environment when you are done with the test:

   ```bash
   deactivate
   ```

8. **Delete the Virtual Environment [OPTIONAL]**

    If you no longer need the virtual environment, you can delete it:

    ```bash
    # Navigate to the directory where venv is created in Step 1
    rm -rf venv
    ```

