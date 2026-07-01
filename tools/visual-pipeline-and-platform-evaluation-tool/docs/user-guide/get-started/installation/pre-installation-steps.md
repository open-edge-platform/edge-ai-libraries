# Pre-Installation Steps

This page lists configuration tasks to consider before starting ViPPET. Some are mandatory,
others are optional and enable specific features.

ViPPET will start and run without any of the optional steps below. Skip the ones you do not
need.

## Mandatory Steps

There are no mandatory pre-installation steps beyond what is already covered in the
installation guides:

- [Use Pre-Built Docker Images](./docker-compose.md)
- [Build from Source](./build-from-source.md)

## Optional Steps

### Hugging Face token (for downloading models from Hugging Face Hub)

ViPPET delegates model installation to the `model-download` service, which supports several
hubs (for example `huggingface`, `ultralytics`, `pipeline-zoo-models`, `openvino`, `geti`,
`hls`). To install models hosted on the **Hugging Face Hub**, especially gated or private
repositories, the `model-download` service must be configured with a valid Hugging Face
access token.

Without a token, ViPPET still runs normally and you can install models from the other
supported hubs. Only the Hugging Face download functionality is disabled.

#### Get a token

1. Sign in (or create an account) at [https://huggingface.co](https://huggingface.co).
2. Open **Settings -> Access Tokens** and create a new token. A token with the **read** role
   is sufficient to download public and gated models.
3. For any gated model, additionally accept its license on the model's Hugging Face page
   while signed in with the same account.

#### Configure the token

Provide the token to the `model-download` service through the `HF_TOKEN` environment
variable. Pick one of the two options below.

##### Option A - shell environment variable (recommended)

Export the variable in the shell before starting the stack. Docker Compose picks it up
automatically because `compose.yml` already declares
`HF_TOKEN: ${HF_TOKEN:-}` for the `model-download` service.

```bash
export HF_TOKEN="hf_your_token_here"
make run
```

To make the variable persistent, add the `export` line to `~/.bashrc`, `~/.zshrc`, or your
preferred shell startup file.

##### Option B - edit `compose.yml`

Open `compose.yml`, locate the `model-download` service, and replace the default value with
your token:

```yaml
services:
  model-download:
    environment:
      HF_TOKEN: hf_your_token_here
```

Do not commit the modified `compose.yml` to a public repository.

#### Apply the change

`HF_TOKEN` is read by the `model-download` container at startup. After setting or changing
the token, restart the whole stack so the new value is picked up:

```bash
make stop run
```

A simple `docker compose restart model-download` is **not** enough if you also changed
`compose.yml`, because Compose needs to re-read the file. Using `make stop run` always works.
