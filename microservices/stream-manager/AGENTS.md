## Project Overview
Stream Manager is a microservice responsible for managing video streams, including their configuration, recording, and storage. Several Intel Open Edge Platform applications consume its REST APIs to interact with and control video streams.

It provides endpoints for buffering an existing RTSP stream, updating the buffer size, record the buffered and live RTSP stream on disk (and also to S3-compatible storage) and retrieval clips or frames from recorded streams for given timestamps.

## Pre-requisites

Before entertaining any user request or instructions for this project, please make sure for following two pre-requisites.

- This is a go project. Hence, requires `golang 1.26` installed on the host machine. If not installed, offer user to install `go` and install the required version along with the tools mentioned in `.pre-commit-config.yaml` file. If user says no, do not install anything.
- Verify if `docker` is installed on the host machine. This could be required as user might want to run the application as a container in order to use it with other microservices. User also might want to build the image themselves. If `docker` is not installed, offer the user to install `docker v29` or a any version later than this. If user agrees, install `docker` on the host machine with the specified version.

## Repository Structure
The repository is structured as follows:
- `cmd/`: Contains the main application entry point.
- `internal/`: Contains the core application logic, including stream management, recording, and storage handling.
- `docs/`: Contains project documentation.
- `Dockerfile`: Dockerfile for containerizing the application.
- `README.md`: Project overview and instructions.
- `AGENTS.md`: General notes, instructions and guidelines for AI Agents.
- `.github` : Contains instructions for interacting with copilot agents.
- `config.json`: Contains the user-provided configuration for the application.
- `go.mod`, `go.sum`: Go module files for dependency management.

It also contains .Dockerignore and .gitignore files for ignoring unnecessary files in Docker builds and Git version control, respectively. The application may also contain `TODO.md` for tracking pending tasks and improvements. `TODO.md` should never be considered while development unless explicitly referenced.

## Build
You can either build on host or build a container image:

### Build on Host
To build the application, you need to run the build command with some linker flags for smaller binaries and to set some essential build-time variables:

```bash
go build -ldflags "-s -w -X main.Version=$(git describe --tags) -X main.BuildNumber=$(git rev-list --count HEAD -- .) -X main.BuildDate=$(date +%Y-%m-%dT%H:%M:%S%z)" -o ./bin/stream-manager ./cmd/api-server
```

This is should build the application binary in ./bin/stream-manager.

### Build a docker container image

There is a `Dockerfile` provided for building the Docker container image in root of the project. Use this to build a docker image as follows:

1. Ask the user for docker image name and tag, also suggesting default image tag (`stream-manager:latest-dev`). If user presses enter without providing any input, use the default image tag.
2. Build the docker image using the provided name and tag and the required build args:

```bash
docker build --build-arg VERSION=$(git describe --tags) --build-arg BUILD_NUMBER=$(git rev-list --count HEAD -- .) -t <image-name>:<tag> .
```

This should build the Docker image with the specified name and tag.

### Handling Build Issues

If there are any errors or issues during build process, analyze the errors and try to root-cause the issue. Handle the errors appropriately and ensure all dependencies are correctly installed. In case of persistent issues, refer to the project documentation. Also explain to user, the reason of failure in a clear, comprehensive and conceptual manner and help them with further actions to get the issue fixed.

## Setup Commands

Application can be setup standalone. However, its primary goal for setup is to use this application along with other microservices in the system. This application will help different microservices in the system by acting as storage and buffering service for streaming data.

### Setting Up as standalone container

1. Decide on what port application should be exposed - Prefer choosing an ephemeral port.

2. If you can't find the image for stream-manager locally, give users following three choices:
    a) First ask for the image name and tag you might be missing
    b) If not ask user whether they want to build the image first before running
    c) If not ask user whether pull it from the remote repository provided by user.

3. Configure if you want to provide a docker volume or a bind mount for persistent storage for the media/database of the application.
    a) For a docker volume you will use this in your `docker run` command: `-v <volume-name>:<container-path>`
    b) For a bind mount, first make sure the directory you are planning to use exists and has proper ownership (for distroless image, directory should be owned by uid/gid 65532). This is very important otherwise writes to the volume will fail.
        i)  Set the ownership of the directory using the command :
            ```bash
            sudo chown -R 65532:65532 <directory-path>
            ```
        ii) Then you will use the directory path in your `docker run` command as a bind mount: `-v <directory-path>:<container-path>`

4. If a config file is available, ask users if they want to mount it to the container to override the default configuration. If yes, your docker run command will include another bind mount: `-v <config-file-path>:/config.json`

5. Run the container with the specified port and volume/mount configurations, using the following command:
```bash
docker run -p <host-port>:<container-port> -v <volume-or-directory-path>:/data -v <config-file-path>:/config.json <image-name>:<tag>
```
Please note the mount to `/data` or `/config.json` in the container is only provided if user wants it for persistent storage or configuration override respectively.

6. Once the setup is complete, verify that the container is running correctly by checking its status. Also hit the `v1/status` endpoint to verify the service is up and running. If everything is fine, tell user how to access the application from host and from a remote machine.


### Setting Up on Host Machine

1. Ensure all dependencies required by the application are installed on the host machine.

2. Verify the necessary dir mentioned in config.json (if used) exists and has the correct ownership (e.g. to allow the application to write into the `StorageDir`).

3. If any configuration file is used, ensure it is accessible and has the correct permissions for the application to read it. If user has provided some custom config values use that by using a temp config file with the requested custom values. You will need to set an env var `SM_CONFIG_FILE` to change the default location of config file. Do not change the `config.json` file present in current dir. Prefer to keep this custom config file in User home config dir.

4. Look for the built binary in the `./bin` directory. If available run the application using `./bin/<binary-name>`. Make sure to tell user that pre-built binary is available and is being used to run the application.

5. If pre-built binary is not available, build the application using the step described in the section [Build on Host](#build-on-host).

6. Once the application is running, verify that application is live by hitting the `v1/status` endpoint. If successful, tell user how to access the application from the host and a remote machine.

### Handling Setup Issues

If there are any errors or issues during setup process, deep-dive and analyze the errors to root-cause the issue. Ensure all dependencies are correctly installed. look for possible edge cases. Check for any failing tests and try to fix them. In case of persistent issues, refer to the project documentation. Also explain to user, the reason of failure in a clear, comprehensive and conceptual manner and help them with further actions to get the issue fixed.

## Code Style

Following principles, styles and guidelines should be strictly followed while writing code :

- Maintain high code quality standards throughout this project, for any change, feature, fix or development task requested.
- Avoid bloated, complex implementation at all cost. Never fall for solutions which are over-engineering or overkill for the given use-case.
- Weigh in all tradeoffs during decision making. Always look at the application context or the use-case at hand to identify actual bottlenecks.
- Separate structural changes from behavioral changes. Follow the Kent Beck's "Tidy First" approach for this.
- Use meaningful variable and function names. These names should eliminate the need for comments in general (but, put comments if really required). That means write explicit functions, variables, object, structs, fields that behaviour and functionality is mostly evident from the naming itself.
- Use comments only if extremely necessary. Keep the code elegant, simple, intuitive and self-comprehensible. When it is extremely hard to keep the code intuitive, use meaningful but brief concise and to-the-point comments. Avoid comments spanning across multiple lines, unless extremely necessary.
- Changes should be separated in two categories:
    - **1. Structural Changes** : Changing/rearranging code without changing behaviour (e.g. renaming, extracting methods, moving etc.).
    - **2. Behavioral Change** : Adding/changing/updating the functionality of application. When both are needed - always do the structural changes first.

### Guidelines to maintain code quality

- Eliminate duplication ruthlessly.
- Express intent clearly through naming and structure.
- Make dependencies explicit.
- Keep methods small and focused on a single responsibility.
- Avoid un-necessary and irrelevant abstractions.
- Avoid creating long change of indirections of function calls, unless required by design.
- Minimize state and side effects.
- Use simple or simplest possible solution that could work instead of over-engineering a complex solution.

## Testing Instructions

- Write tests rigorously for all the functionality and integration requirements.
- Run all tests after any changes made to the application code, to make sure nothing breaks after the change.
- Run end to end all functional and integration tests before committing any change.

## Linting

The application has pre-commit hooks configured, which lints and vets the application at each commit for any possible issues. However, follow linting and other required code-level checks pro-actively and use these tools after every change made by you, irrespective of whether it is committed or not. Keep the imports clean, modules tidy after every change. Use the tools used by pre-commit hooks to run the linters and other checkers. If not available look for GOPATH env and run the tools from there. If not installed, install the tools after taking permission from the user.

## Commit and Pull Request Guidelines

### Commit Discipline

- Do not use any skills to commit the code, even if explicitly invoked.
- Only commit when :
    - linting checks and function/integration tests are passing
    - All compiler/linker warnings are resolved.
- Each commit should represent a single logical unit of work.
- Never commit structural and behavioral changes in same commit.
- Commit messages should clearly indicate about structural or behavioral change.
- Write precise and brief, but descriptive commit messages to explain all change going into commit. Never write more than 5-6 lines at most in any commit message.
- Never add any co-authors in the commit which are not humans.
- Use small frequent commits rather than a large infrequent commit.

### Pull Request Guideline

- Create pull request only when explicitly asked for.
- Follow the pull request guidelines for Open Edge Platform strictly.
- Write a brief yet comprehensive description of the pull request which clearly defines what this pull request changes, fixes, updates or any new features are introduced.
- Give a short precise title for the PR always starting with text `[stream-manager]`.


## Security Considerations

- Have security first mindset.
- Always test any new change, fix, or new feature implementation for any potential security loopholes. Explicitly call out these risks or loopholes.
- Provide user the mitigation steps with clear detailed explanation for any such potential issues found during the code writing or implementation.
- Always look for any vulnerable dependency having medium, high or critical CVEs when creating pull-requests. If found, alert the user and suggest the ways to mitigate the CVE before creating the pull request.

## Documentation

### Principles to follow to write documentation

- Use ASD-STE100 standard (used for writing aircraft manuals in Simplified Technical English), strictly throughout the whole documentations for simple, comprehensive, unambiguous writing for using this application.
- Use following principles of writing strictly without any fail:
    - Use simplest most unambiguous english possible.
    - One word, one meaning.
    - Do not use any synonyms.
    - Short sentences.
    - One action per step.
    - Use active voice only.
    - No omitted words.
    - Do not reveal internal details for implementation, unless specifically and explicitly stated.
    - Clearly distinguish and emphasize - WARNING, CAUTION, and NOTE. They should be clearly defined and should not intermix (eg. something meant as WARNING should not be written as NOTE).


### Documentation structure

Following is the guidelines regarding the directory structure of the documentation. They are primarily present inside the `docs` dir in root. A single `README.md` file in project root is also present. If these files are not present at their respective location, please create it when asked to write documentation of the application.

#### README.md
- This file `README.md` is present in the root of the project.
- Start with extremely brief, concise yet brilliant, comprehensive and unambiguous explanation of the application for why it exists.
- Write a README file which contains the quick start section and links and small description to all documents inside the `docs` directory (except the `index.md` file)
- Quick start section aims to give user a possible one-click solution for quickly spinning up the application.

#### Get started Guide

- This file `get-started.md` lives in `docs/user-guide` directory.
- It tells you all possible details of setting up and using the application, like a simple user manual of an appliance. This does not include the building guidelines and assumes that application is present as an image in a public repository `intel/stream-manager:latest`. Use this information to instruct user to pull and use this image to run the application. Add details about overriding `config.json` and using volume mount or bind-mount for letting the application persist media and database files.

#### API Reference Guide

- API reference document is available at `docs/api-docs/api-reference.md`.
- Keep updating the `docs/api-docs/api-reference.md` and `docs/api-docs/openapi.yaml` document as the api specs and implementation keeps changing or updating.

#### Build from Source Guide

- Build from source guide should be present at the `docs/user-guide/build-from-source.md`.
- This document guides user clearly towards how to build the application on host and how to build a container image. Refer to the [Build](#build) section here and other information available to write a well designed guide.

#### Openapi Specs

- `openapi.yaml` file lives in the `docs/user-guide/api-docs/openapi.yaml` file.
- This contains the YAML content read by the gin-swagger tool to present the Swagger UI for using the API along with all the API specification, request and response schemas, sample request and response examples, and error codes with corresponding error response.
- Wehenevr asked to update the Swagger UI or openapi specs - Keep the YAML file upto date with the actual implementation of API routes and schema, request body, response body and error code/response being used.
- Apart from explicitly being asked, update or work on it to sync with the changes whenever asked to update the documentation.

## Agent-Specific Notes

Read the (`copilot-instructions.md`)[.github/copilot-instructions.md] for guidance on how to interact with the copilot agents.

## Additional Notes

- Never implement or act on `TODO.md` unless explicitly told to.
