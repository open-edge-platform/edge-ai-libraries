# Running Tests for PGVector Document Ingestion

This guide will help you run the tests for the PGVector Document Ingestion service using the pytest framework.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Running Tests in a Virtual Environment [RECOMMENDED]](#running-tests-in-a-virtual-environment-recommended)
- [Running Tests without a Virtual Environment](#running-tests-without-a-virtual-environment)
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

1. **Install `venv` for python virtual environment creation**

   ```bash
   sudo apt install python3.11-venv
   ```

2. **Create a Virtual Environment**

    Navigate to your project directory and create a virtual environment using `venv`:

    ```bash
    python -m venv venv
    ```

3. **Activate the Virtual Environment**

    Activate the virtual environment:
    - On Linux:

      ```bash
      source venv/bin/activate
      ```

4. **Clone the Repository**

   Clone the repository to your local machine:

   ```bash
   # Clone the latest on mainline
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, Clone a specific release branch
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
   ```

5. **Install the Required Packages**

    With the virtual environment activated, install the required packages:

    ```bash
    # Install application dependencies packages using Poetry
    cd edge-ai-libraries/microservices/document-ingestion/pgvector
    poetry install --with dev
    ```

6. **Setup Environment Variables**

   Setup the environment variables:

   ```bash
   export HUGGINGFACEHUB_API_TOKEN=<your_huggingface_token>

   source run.sh --nosetup
   ```

7. **Navigate to the Tests Directory**

   Change to the directory containing the tests:

   ```bash
   cd tests/unit_tests
   ```

8. **Run the Tests**

   Use the `pytest` command to run the tests:

   ```bash
   pytest
   ```

   This will discover and run all the test cases defined in the `tests` directory.

9. **Deactivate Virtual Environment**

   Remember to deactivate the virtual environment when you are done with the test:

   ```bash
   deactivate
   ```

10. **Delete the Virtual Environment [OPTIONAL]**

    If you no longer need the virtual environment, you can delete it:

    ```bash
    # Navigate to the directory where venv is created in Step 1
    rm -rf venv
    ```

---

## Running Tests without a Virtual Environment

If you prefer not to use virtual environment, please follow these steps:

1. **Clone the Repository**

    First, clone the repository to your local machine:

    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
    ```

2. **Install the application dependencies**

   Navigate to the project directory and run the following commands:

   ```bash
   # Install application dependencies packages
   cd edge-ai-libraries/microservices/document-ingestion/pgvector
   poetry install --with dev
   ```

3. **Setup Environment Variables**

   Setup the environment variables:

   ```bash
   export HUGGINGFACEHUB_API_TOKEN=<your_huggingface_token>

   source run.sh --nosetup
   ```

4. **Navigate to the Tests Directory**

    Change to the directory containing the tests:

    ```bash
    cd tests/unit_tests
    ```

5. **Run the Tests**

    Use the `poetry run pytest` command to run the tests:

    ```bash
    poetry run pytest
    ```

    This ensures pytest runs within the virtual environment without needing to activate it separately.

    Alternatively, you can manually activate the environment and then run the tests:

    ```bash
    # activate the environment
    eval $(poetry env activate)
    # run the tests
    pytest
    # deactivate the environment after running the tests
    deactivate
    ```

    This will discover and run all the test cases defined in the `tests` directory.
