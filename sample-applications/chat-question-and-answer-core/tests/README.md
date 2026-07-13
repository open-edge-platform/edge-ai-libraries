# Running Tests for Chat Q&A Core

This guide will help you run the tests for the Chat Q&A Core project using the pytest framework.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Running Backend Tests](#running-backend-tests)
- [Running Tests for UI](#running-tests-for-ui)

---

## Prerequisites

Before running the tests, ensure you have the following installed:

- For backend
   - Python 3.11+
    - `uv` (Python package and project manager)
- For UI
   - `npm` (Node package manager)
   - `vitest` (Next generation testing framework)

## uv Installation
You can install uv using one of the following commands:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

# or with pip
pip install uv
```

## Node and `npm` Installation
```bash
# Download and install nvm:
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash

# In lieu of restarting the shell
\. "$HOME/.nvm/nvm.sh"

# Download and install Node.js:
nvm install 22

# Verify the Node.js version:
node -v # Should print "v22.14.0".
nvm current # Should print "v22.14.0".

# Verify npm version:
npm -v # Should print "10.9.2".
```

---

## Running Backend Tests

If you prefer to run the tests in a project virtual environment, follow these steps:

1. **Clone the Repository**

    Clone the repository to your local machine:

    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
    ```

2. **Install the Required Packages**

    Navigate to the project directory and sync dependencies with uv.
    Install all dependency groups required for backend unit testing:

    ```bash
    cd edge-ai-libraries/sample-applications/chat-question-and-answer-core/

    uv sync --all-groups
    ```

3. **Navigate to the Tests Directory**

    Change to the directory containing the tests:

    ```bash
    cd <repository-url>/sample-applications/chat-question-and-answer-core/tests
    ```

4. **Run the Tests**

    Use `uv run pytest` to run the tests in the uv-managed virtual environment, with support for different model backends.

    You can specify a model backend using the `--model-runtime` option. This allows test to dynamically configure dummy model settings and skip non-related tests when neccessary.

    For more detailed output—including the names of individual tests and their statuses—you can use the --verbose flag:
    ```bash
    # To run openvino-related tests
    uv run pytest --model-runtime=openvino

    # To run ollama-related tests
    uv run pytest --model-runtime=ollama

    Some tests are designed to run only for specific backends. Hence, these test cases will get triggered based on `--model-runtime` configured.

5. **Run Tests with Coverage Report**

    To generate a backend coverage report, run:

    ```bash
    # openvino backend
    uv run pytest --model-runtime=openvino --cov=app --cov-report=term-missing

    # ollama backend
    uv run pytest --model-runtime=ollama --cov=app --cov-report=term-missing
    ```

    To generate with an HTML coverage report, run:

    ```bash
    # openvino backend
    uv run pytest --model-runtime=openvino --cov=app --cov-report=html

    # ollama backend
    uv run pytest --model-runtime=ollama --cov=app --cov-report=html
    ```

    HTML coverage output is generated at `htmlcov/index.html`. Open it in a browser to view the detailed coverage report.

## Running Tests for UI

1. Before executing the following commands, ensure you navigate to the `ui` directory.

    ```bash
    cd <repository-url>/sample-applications/chat-question-and-answer-core/ui
    ```

2. On a fresh clone, install dependencies first (only needed once):

    ```bash
    npm install
    ```

3. Execute the Tests for the UI

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

       This command will produce a detailed coverage report, highlighting the percentage of code covered by the tests. The report will be saved in the `ui/coverage` directory for further review.
