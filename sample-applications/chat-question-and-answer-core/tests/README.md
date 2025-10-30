# Running Tests for ChatQnA-Core

This guide will help you run the tests for the ChatQnA-Core project using the pytest framework.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Running Tests for backend in a Virtual Environment [RECOMMENDED]](#running-tests-for-backend-in-a-virtual-environment-recommended)
- [Running Tests for backend without a Virtual Environment](#running-tests-for-backend-without-a-virtual-environment)
- [Running Tests for UI](#running-tests-for-ui)

---

## Prerequisites

Before running the tests, ensure you have the following installed:

- For backend
   - Python 3.11+
   - `pip` (Python package installer)
   - `Poetry` (Python dependency management and packaging tool)
- For UI
   - `npm` (Node package manager)
   - `vitest` (Next generation testing framework)

## Poetry Installation
You can install Poetry using the following command:

```bash
curl -sSL https://install.python-poetry.org | python3 -
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

## Vitest installation
```bash
npm install -D vitest@3.2.4
```
---

## Running Tests for backend in a Virtual Environment [RECOMMENDED]

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
    cd edge-ai-libraries/sample-applications/chat-question-and-answer-core
    poetry install --with dev --no-root
    ```

6. **Setup the Environment Variables**

    Setup the environment variables:

    ```bash
    # via scripts
    export HUGGINGFACEHUB_API_TOKEN="<YOUR_HUGGINGFACEHUB_API_TOKEN>"
    source scripts/setup_env.sh
    ```

7. **Navigate to the Tests Directory**

    Change to the directory containing the tests:

    ```bash
    cd <repository-url>/sample-applications/chat-question-and-answer-core/tests
    ```

8. **Run the Tests**

    Use the `pytest` command to run the tests, with support for different model backends.

    You can specify a model backend using the `--model-runtime` option. This allows test to dynamically configure dummy model settings and skip non-related tests when neccessary.

    For more detailed output—including the names of individual tests and their statuses—you can use the --verbose flag:
    ```bash
    # To run openvino-related tests
    pytest --model-runtime=openvino --verbose

    # Expected output
    ============================================================================================== test session starts ==============================================================================================
    platform linux -- Python 3.10.12, pytest-8.4.1, pluggy-1.6.0 -- /home/user/edge-ai-libraries/sample-applications/chat-question-and-answer-core/tests/venv/bin/python
    cachedir: .pytest_cache
    rootdir: /home/user/edge-ai-libraries/sample-applications/chat-question-and-answer-core
    configfile: pyproject.toml
    plugins: langsmith-0.4.11, anyio-4.10.0, asyncio-0.24.0, mock-3.14.1
    asyncio: mode=strict, default_loop_scope=module
    collected 16 items

    test_ollama_utils.py::test_get_loaded_ollama_models SKIPPED (Only valid for ollama backend)                                                                                                               [  6%]
    test_ollama_utils.py::test_get_ollama_model_metadata[phi3.5:latest] SKIPPED (Only valid for ollama backend)                                                                                               [ 12%]
    test_ollama_utils.py::test_get_ollama_model_metadata[nomic-embed-text:latest] SKIPPED (Only valid for ollama backend)                                                                                     [ 18%]
    test_ollama_utils.py::test_invalid_ollama_model_id SKIPPED (Only valid for ollama backend)                                                                                                                [ 25%]
    test_openvino_utils.py::test_get_devices PASSED                                                                                                                                                           [ 31%]
    test_openvino_utils.py::test_get_device_properties[CPU] PASSED                                                                                                                                            [ 37%]
    test_openvino_utils.py::test_get_device_properties[GPU] PASSED                                                                                                                                            [ 43%]
    test_openvino_utils.py::test_invalid_device PASSED                                                                                                                                                        [ 50%]
    test_server.py::test_chain_response PASSED                                                                                                                                                                [ 56%]
    test_server.py::test_success_upload_and_create_embedding PASSED                                                                                                                                           [ 62%]
    test_server.py::test_success_get_documents PASSED                                                                                                                                                         [ 68%]
    test_server.py::test_delete_embedding_success PASSED                                                                                                                                                      [ 75%]
    test_server.py::test_delete_all_embedding_success PASSED                                                                                                                                                  [ 81%]
    test_server.py::test_upload_unsupported_file PASSED                                                                                                                                                       [ 87%]
    test_server.py::test_fail_get_documents PASSED                                                                                                                                                            [ 93%]
    test_server.py::test_delete_embedding_failure PASSED                                                                                                                                                      [100%]

    ========================================================================================= 12 passed, 4 skipped in 6.01s =========================================================================================

    # To run ollama-related tests
    pytest --model-runtime=ollama --verbose

    # Expected output
    ============================================================================================== test session starts ==============================================================================================
    platform linux -- Python 3.10.12, pytest-8.4.1, pluggy-1.6.0 -- /home/user/edge-ai-libraries/sample-applications/chat-question-and-answer-core/tests/venv/bin/python
    cachedir: .pytest_cache
    rootdir: /home/user/edge-ai-libraries/sample-applications/chat-question-and-answer-core
    configfile: pyproject.toml
    plugins: langsmith-0.4.11, anyio-4.10.0, asyncio-0.24.0, mock-3.14.1
    asyncio: mode=strict, default_loop_scope=module
    collected 16 items

    test_ollama_utils.py::test_get_loaded_ollama_models PASSED                                                                                                                                                [  6%]
    test_ollama_utils.py::test_get_ollama_model_metadata[phi3.5:latest] PASSED                                                                                                                                [ 12%]
    test_ollama_utils.py::test_get_ollama_model_metadata[nomic-embed-text:latest] PASSED                                                                                                                      [ 18%]
    test_ollama_utils.py::test_invalid_ollama_model_id PASSED                                                                                                                                                 [ 25%]
    test_openvino_utils.py::test_get_devices SKIPPED (Only valid for openvino backend)                                                                                                                        [ 31%]
    test_openvino_utils.py::test_get_device_properties[CPU] SKIPPED (Only valid for openvino backend)                                                                                                         [ 37%]
    test_openvino_utils.py::test_get_device_properties[GPU] SKIPPED (Only valid for openvino backend)                                                                                                         [ 43%]
    test_openvino_utils.py::test_invalid_device SKIPPED (Only valid for openvino backend)                                                                                                                     [ 50%]
    test_server.py::test_chain_response PASSED                                                                                                                                                                [ 56%]
    test_server.py::test_success_upload_and_create_embedding PASSED                                                                                                                                           [ 62%]
    test_server.py::test_success_get_documents PASSED                                                                                                                                                         [ 68%]
    test_server.py::test_delete_embedding_success PASSED                                                                                                                                                      [ 75%]
    test_server.py::test_delete_all_embedding_success PASSED                                                                                                                                                  [ 81%]
    test_server.py::test_upload_unsupported_file PASSED                                                                                                                                                       [ 87%]
    test_server.py::test_fail_get_documents PASSED                                                                                                                                                            [ 93%]
    test_server.py::test_delete_embedding_failure PASSED                                                                                                                                                      [100%]

    ========================================================================================= 12 passed, 4 skipped in 1.19s =========================================================================================
    ```

    Some tests are designed to run only for specific backends. Hence, these test cases will get triggered based on `--model-runtime` configured.

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

## Running Tests for backend without a Virtual Environment

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
    cd edge-ai-libraries/sample-applications/chat-question-and-answer-core/
    poetry install --with dev --no-root
    ```

3. **Setup the Environment Variables**

    Setup the environment variables:

    ```bash
    # via scripts
    export HUGGINGFACEHUB_API_TOKEN="<YOUR_HUGGINGFACEHUB_API_TOKEN>"
    source scripts/setup_env.sh
    ```

4. **Navigate to the Tests Directory**

    Change to the directory containing the tests:

    ```bash
    cd <repository-url>/sample-applications/chat-question-and-answer-core/tests
    ```

5. **Run the Tests**

    Use the `poetry run pytest` command with `--model-runtime` option to run the tests with support of different model backends.

    This allows test to dynamically configure dummy model settings and skip non-related tests when neccessary.

    ```bash
    # To run openvino-related tests
    poetry run pytest --model-runtime=openvino --verbose

    # To run ollama-related tests
    poetry run pytest --model-runtime=ollama --verbose
    ```

    This ensures pytest runs within the virtual environment without needing to activate it separately.

    Alternatively, you can manually activate the environment and then run the tests:

    ```bash
    # activate the environment
    eval $(poetry env activate)

    # run the tests
    # run openvino-related tests
    pytest --model-runtime=openvino --verbose

    # run ollama-related tests
    pytest --model-runtime=ollama --verbose

    # deactivate the environment after running the tests
    deactivate
    ```

    This will discover and run all the test cases defined in the `tests` directory.

## Running Tests for UI

1. Before executing the following commands, ensure you navigate to the `ui` directory.

    ```bash
    cd <repository-url>/sample-applications/chat-question-and-answer-core/ui
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

       This command will produce a detailed coverage report, highlighting the percentage of code covered by the tests. The report will be saved in the `ui/coverage` directory for further review.
