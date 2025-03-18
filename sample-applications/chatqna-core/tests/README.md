# Running Tests for ChatQnA-Core

This guide will help you run the tests for the ChatQnA-Core project using the pytest framework.

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
   git clone https://github.com/intel-innersource/applications.ai.intel-gpt.generative-ai-examples.git
   ```

5. **Install the Required Packages**

    With the virtual environment activated, install the required packages:

    ```bash
    # Install application dependencies packages using Poetry
    cd ~/applications.ai.intel-gpt.generative-ai-examples/sampleapps/chatqna-core
    poetry install --with dev
    ```

6. **Setup the Environment Variables**

   Setup the environment variables:

   ```bash
   # via scripts
   export HUGGINGFACE_API_TOKEN="<YOUR_HUGGINGFACE_API_TOKEN>"
   source scripts/setup_env.sh
   ```

7. **Navigate to the Tests Directory**

   Change to the directory containing the tests:

   ```bash
   cd applications.ai.intel-gpt.generative-ai-examples/sampleapps/chatqna-core/tests
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
    git clone https://github.com/intel-innersource/applications.ai.intel-gpt.generative-ai-examples.git
    ```

2. **Install the application dependencies**

   Navigate to the project directory and run the following commands:

   ```bash
   # Install application dependencies packages
   cd ~/applications.ai.intel-gpt.generative-ai-examples/sampleapps/chatqna-core/
   poetry install --with dev
   ```

3. **Setup the Environment Variables**

   Setup the environment variables:

   ```bash
   # via scripts
   export HUGGINGFACE_API_TOKEN="<YOUR_HUGGINGFACE_API_TOKEN>"
   source scripts/setup_env.sh
   ```

4. **Navigate to the Tests Directory**

    Change to the directory containing the tests:

    ```bash
    cd applications.ai.intel-gpt.generative-ai-examples/sampleapps/chatqna-core/tests
    ```

5. **Run the Tests**

    Use the `pytest` command to run the tests:

    ```bash
    pytest
    ```

    This will discover and run all the test cases defined in the `tests` directory.
