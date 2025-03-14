# Intel ChatQnA UI

Welcome to the ChatQnA UI project! This guide will help you set up and run the ChatQnA UI application using `Docker` or, `npm`. Follow the steps below to ensure a smooth deployment process.

**Note:** This **README** is helpful if you only want to run the UI services and you already have the **Backend and Data prep service endpoint**. If you want to run all the services then you should read this [**README**](/sampleapps/chatqna/README.md).

## Prerequisites

Before you begin, ensure you have the following installed on your machine:

- Docker (if running with Docker)
- npm (if running without Docker)
- Backend service endpoint
- Data prep service endpoint

## Setup Instructions

#### Step 1: Update the `.env` File

To run the UI locally, update the `.env` file located in the `ui/react` directory of the project. Add the following environment variables with the appropriate endpoint values:

```bash
VITE_BACKEND_SERVICE_ENDPOINT=http://$HOST_IP:8100
VITE_DATA_PREP_SERVICE_URL=http://$HOST_IP:8000
```

### Running with Docker

#### Step 2: Build the Docker Image

Navigate to the root directory `ui/react` of the project and build the Docker image using the following command:

```bash
docker build -t <docker_image_name> .
```

#### Step 3: Run the Docker Container

To run the Docker container, use the following command:

```bash
docker run -p <your_port>:80 <docker_image_name>
```

Replace `<your_port>` with the port number you want to use for accessing the UI.

Upon successfully executing this command, you can access the UI services at the URL displayed in the terminal, typically `http://localhost:<your_port>`.

### Running without Docker

#### Step 2: Install Dependencies

Navigate to the `ui/react` directory of the project and install the necessary dependencies using npm:

```bash
npm install
```

#### Step 3: Run the Application

To run the application, use the following command:

```bash
npm run dev
```

Upon successfully executing this command, you can access the UI services at the URL displayed in the terminal, typically http://localhost:5173.

## How to Run Unit Test Cases for the UI

Ensure that your `package.json` includes the following scripts before running the unit test cases.

```bash
"scripts": {
  "test": "vitest",
  "test:ui": "vitest --ui",
  "coverage": "vitest run --coverage"
}
```

### Running Unit Test Cases

1. **Running Test Cases in the Command Line:**
   Use the following command to run the test cases from the command line:

   ```bash
   npm run test
   ```

   This command will execute all the test cases using `Vitest` and display the results in the terminal.

2. **Running Test Cases in the UI:**
   Use the following command to run the test cases from the command line and see the results in the UI:

   ```bash
   npm run test:ui
   ```

   This command will launch the Vitest UI, providing a graphical interface to run and monitor your test cases.

3. **Viewing Test Coverage:**
   To view the test coverage with `istanbul`, run the following command:

   ```bash
   npm run coverage
   ```

   This command generates a coverage report, indicating the percentage of code covered by tests. The report will be located in the `coverage` directory.
   Upon successfully executing this command, you can access the UI services at the URL displayed in the terminal, typically http://localhost:5173.

### Conclusion

By following these steps, you will have the ChatQnA UI application up and running in no time.

Thank you for using ChatQnA UI!
