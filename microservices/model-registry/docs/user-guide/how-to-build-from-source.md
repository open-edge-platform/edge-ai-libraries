```{eval-rst}
:orphan:
```
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

1. **Define the desired values for the REQUIRED environment variables in the `.env` file:**
    1. `MR_MINIO_ACCESS_KEY`
    2. `MR_MINIO_SECRET_KEY`
    3. `MR_PSQL_PASSWORD`

    * For more information about the supported the environment variables, refer to the [Environment Variables](./environment-variables.md) documentation.

1. **Create a virtual environment**
    ```bash
    virtualenv -p /usr/bin/python3.10 myvenv
    ```

2. **Activate the virtual environment**
    ```bash
    source myvenv/bin/activate
    ```
3. **Install the dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4. **Create the Docker containers for the **PostgreSQL** and **MinIO** services**
    ```bash
    docker compose -f docker-compose-dev.yml up -d mr_postgres mr_minio
    ```
    * Docker containers for **PostgreSQL** and **MinIO** are required for the model registry to execute operations successfully.

5. **Load the environment variables defined in the `.env` file into the current Terminal session**
    ```bash
    source .env
    ```
    
6. **Start the microservice**
    ```bash
    # Replace `{{path_to}}` with the actual path to the directory
    cd {{path_to}}/src/
    
    python main.py
    ```

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

2. **Access the Microservice**:
   - Open a browser and go to:
     ```
     http://localhost:{{port}}/docs
     ```
   - Expected result: The microservice’s API documentation loads successfully.


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
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
