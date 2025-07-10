## Running Tests for Video Search Microservice

The project uses pytest for testing. After installing and setting up the application on host, we can run tests as follows:

### Prerequisites
1. Ensure you are in the search-ms directory:
   ```bash
   cd edge-ai-libraries/sample-applications/video-search-and-summarization/search-ms
   ```

2. Install dependencies using Poetry:
   ```bash
   poetry install
   ```

3. Activate the virtual environment:
   ```bash
   poetry shell
   ```

### Test Directory Structure
```
src/tests/
├── README.md                    # This file
├── conftest.py                  # Test configuration and fixtures
├── test_utils/                  # Utility function tests
│   ├── test_common.py
│   ├── test_directory_watcher.py
│   ├── test_minio_client.py
│   └── test_utils.py
└── test_vdms_retriever/         # VDMS retriever tests
    ├── test_embedding_wrapper.py
    └── test_retriever.py
```

### Running Tests

# Run all tests
python -m pytest src/tests/

# Run tests with verbose output
python -m pytest src/tests/ -v

# Run tests by module - Utils
python -m pytest src/tests/test_utils/test_common.py
python -m pytest src/tests/test_utils/test_directory_watcher.py
python -m pytest src/tests/test_utils/test_minio_client.py
python -m pytest src/tests/test_utils/test_utils.py

# Run tests by module - VDMS Retriever
python -m pytest src/tests/test_vdms_retriever/test_embedding_wrapper.py
python -m pytest src/tests/test_vdms_retriever/test_retriever.py

# Run all tests in utils directory
python -m pytest src/tests/test_utils/

# Run all tests in vdms_retriever directory
python -m pytest src/tests/test_vdms_retriever/

# Run specific test class
python -m pytest src/tests/test_utils/test_common.py::TestCommon

# Run specific test method
python -m pytest src/tests/test_utils/test_common.py::TestCommon::test_settings_default_values

## Test Coverage Reports
To generate a coverage report:

# Run tests with coverage
python -m pytest src/tests/ --cov=src

# Generate detailed HTML coverage report
python -m pytest src/tests/ --cov=src --cov-report=html --cov-report=term-missing

