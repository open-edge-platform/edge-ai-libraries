# Running Tests for ChatQnA

This guide will help you run the tests for the ChatQnA project using the pytest framework.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Running Tests in a Virtual Environment [RECOMMENDED]](#running-tests-in-a-virtual-environment-recommended)
- [Running Tests without a Virtual Environment](#running-tests-without-a-virtual-environment)
- [Running Tests for UI](#running-tests-for-ui)

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
   git clone <repository-url> -b release-1.2.0
   ```

5. **Install the Required Packages**

    With the virtual environment activated, install the required packages:

    ```bash
    # Install application dependencies packages using Poetry
    cd ~/<repository-url>/sample-applications/chat-question-and-answer
    poetry install --with dev
    ```

6. **Setup the Environment Variables**

   Setup the environment variables:

   ```bash
   # via scripts
    export HUGGINGFACE_API_TOKEN="<YOUR_HUGGINGFACE_API_TOKEN>"
    export LLM_MODEL=Intel/neural-chat-7b-v3-3
    export EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
    export RERANKER_MODEL=BAAI/bge-reranker-base
    source setup.sh llm=<ModelServer> embed=<Embedding>
   ```

7. **Navigate to the Tests Directory**

   Change to the directory containing the tests:

   ```bash
   cd <repository-url>/sample-applications/chat-question-and-answer/tests/unit_tests
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
    git clone <repository-url> -b release-1.2.0
    ```

2. **Install the application dependencies**

   Navigate to the project directory and run the following commands:

   ```bash
   # Install application dependencies packages
   cd ~/<repository-url>/sample-applications/chat-question-and-answer
   poetry install --with dev
   ```

3. **Setup the Environment Variables**

   Setup the environment variables:

   ```bash
   # via scripts
   export HUGGINGFACE_API_TOKEN="<YOUR_HUGGINGFACE_API_TOKEN>"
   export LLM_MODEL=Intel/neural-chat-7b-v3-3
   export EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
   export RERANKER_MODEL=BAAI/bge-reranker-base
   source setup.sh llm=<ModelServer> embed=<Embedding>
   ```

4. **Navigate to the Tests Directory**

    Change to the directory containing the tests:

    ```bash
    cd <repository-url>/sample-applications/chat-question-and-answer/tests/unit_tests
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

## Running Tests for UI

1. Before executing the following commands, ensure you navigate to the `ui` directory.
   ```bash
   cd <repository-url>/sample-applications/chat-question-and-answer/ui/react
   ```

2. Execute the Tests for the UI
   - **Running Test Cases via the Command Line:**
      To execute all test cases from the command line, use the following command:

      ```bash
      npm run test
      ```

      This command will run all test cases using the `Vitest` testing framework and display the results directly in the terminal.

   - **Running Test Cases with a Graphical Interface:**
      To run test cases and monitor results through a graphical user interface, use the following command:

      ```bash
      npm run test:ui
      ```

      This will launch the `Vitest` UI, providing an interactive interface to execute and review test results.

   - **Viewing Code Coverage Reports:**
      To generate and view a code coverage report, execute the following command:

      ```bash
      npm run coverage
      ```

      This command will produce a detailed coverage report, highlighting the percentage of code covered by the tests. The report will be saved in the `coverage` directory for further review.