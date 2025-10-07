<!--hide_directive```{eval-rst}
:orphan:
```hide_directive-->

# How to Build from Source

Build the Model Registry from source to customize, debug, or extend its functionality. In this guide, you will:
- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.


## Prerequisites

Before you begin, ensure the following:
- **System Requirements**: Verify your system meets the [minimum requirements](./system-requirements.md).
- **Dependencies Installed**:
    - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
    - **Python 3.8 or higher**: [Python Installation Guide](https://www.python.org/downloads/)
- **Permissions**: Confirm you have permissions to install software and modify environment configurations.

This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
- [Git Documentation](https://git-scm.com/doc)
- [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)


## Steps to Build

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/{{repo-path}}.git

    cd {{repo-name}}
    ```

2. **Install Python 3.10**
    ```bash
    sudo apt-get install python3.10
    ```
1. **Rename the `.env.template` file to `.env`**
    ```bash
    # Replace `{{path_to}}` with the actual path to the directory
    cd {{path_to}}/docker

    mv .env.template .env
    ```
1. **Create the directories to be used as persistent storage for the `PostgreSQL` and `MinIO` containers**
    ```bash
    # Replace `{{path_to}}` with the actual path to the directory
    cd {{path_to}}/scripts

    sudo ./init_mr_data_dirs.sh
    ```

1. **Define the desired values for the REQUIRED environment variables in the `.env` file in the `docker` directory:**
    1. `MR_MINIO_ACCESS_KEY`
    2. `MR_MINIO_SECRET_KEY`
    3. `MR_PSQL_PASSWORD`

    ```bash
    # Replace `{{path_to}}` with the actual path to the directory
    cd {{path_to}}/docker

    vi .env
    ```

    * For more information about the supported the environment variables, refer to the [Environment Variables](./environment-variables.md) documentation.

1. Optional: Enter values for the `http_proxy` and `https_proxy` variables in the `.env` file if you are behind a proxy.
    ```
    http_proxy= # example: http_proxy=http://proxy.example.com:891
    https_proxy= # example: https_proxy=http://proxy.example.com:891
    ```

1. **Load the environment variables defined in the `.env` file into the current Terminal session**
    ```bash
    source .env
    ```

1. **Build the model registry and start the containers**
    ```bash
    docker compose build

    docker compose up -d
    ```

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

2. **Access the Microservice**:
   - Open a browser and go to:
     ```
     http://localhost:{{port}}/docs
     ```
   - Expected result: The microservice’s API documentation page loads successfully.

   For more example requests and their responses, refer to the [Get Started Guide](./get-started.md#storing-a-model-in-the-registry).

## Troubleshooting

1. **Dependency Installation Errors**:
   - Reinstall dependencies:
     ```bash
     pip install -r requirements.txt
     ```

2. **Environment Configuration Issues**:
   - Verify environment variables:
     ```bash
     echo $VARIABLE_NAME
     ```


## Supporting Resources
* [Overview](Overview.md)
* [System Requirements](system-requirements.md)
* [API Reference](api-reference.md)
*
