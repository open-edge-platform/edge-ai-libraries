# Time Series Analytics Microservice

Below, you'll find links to detailed documentation to help you get started, configure, and deploy the microservice.

## Documentation

- **Overview**
  - [Overview](docs/user-guide/Overview.md): A high-level introduction to the Time Series Analytics Microservice.

- **Docker compose Deployment**
  - [Docker compose deployment](docs/user-guide/get-started.md): Instructions for building the microservice from source code.

- **Helm deployment**
  - [Helm deployment](./docs/user-guide/how-to-deploy-with-helm.md): Instructions for advanced configuration.

- **API Reference**
  - [API reference](./docs/user-guide/how-to-access-api.md): Instructions to exercise REST APIs

- **Release Notes**
  - [Release Notes](docs/user-guide/release_notes/Overview.md): Information on the latest updates, improvements, and bug fixes.

## Running Unit tests

Follow the steps below to run the unit tests.

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries
cd edge-ai-libraries/microservices/time-series-analytics
echo "Running unit tests"
./tests/run_tests.sh
```

## Running Functional tests

Follow the steps below to run the functional tests.
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries
cd edge-ai-libraries/microservices/time-series-analytics/tests-functional
echo "Running functional tests"
pip3 install -r requirements.txt
pytest -q -vv --self-contained-html --html=./test_report/report.html .
```