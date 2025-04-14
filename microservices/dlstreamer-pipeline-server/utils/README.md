# generate_tls_certs_keys.sh
**Description**: This shell script creates self-signed certificates and private keys for a certificate authority (CA), and server. It can also optionally create a self-signed certificate and private key for a client.

**Usage**:
```bash
./generate_tls_certs_keys.sh [create_client_cert_key_flag] [server_ip]
```

**Options**:

* -h, --help: Display a help message.

**Arguments**:

* **[create_client_cert_key_flag]** (optional): A flag to indicate whether to create a certificate and private key for a client. The default value is false.
* **[server_ip]** (optional): The IP address of the server to be included in the server and client's certificate. Required if `create_client_cert_key_flag` is true and the client is expected to be hosted on a separate system. This is a common practice in mTLS (Mutual TLS) configurations to establish trust and ensure secure communication between DL Streamer Pipeline Server's REST API server and a client.

**Examples**:
```bash
./generate_tls_certs_keys.sh
```
* The script creates self-signed certificate (\*.crt) and private key (\*.key) files for the CA and DL Streamer Pipeline Server's REST API server in the `Certificates/ssl_server` directory in the project's root directory.

```bash
./generate_tls_certs_keys.sh true
```
* Along with the CA's and server's files, the script creates a self-signed certificate and private key for a client.

```bash
./generate_tls_certs_keys.sh true 192.168.1.100
```
* The provided IP address is included in the OpenSSL configuration (\*.cnf) file for the client and server. It is used in the creation of their certificates. This allows for the client's certificate to be identified by a server with the IP address "192.168.1.100".

# int_mr_dir.sh
**Description**: This shell script makes the `mr_models` directory in the project's root directory, creates a new user based on the value of the `PIPELINE_SERVER_USER` environment variable, and changes the ownership of the `mr_models` directory to the new user. This directory is used as the location for model artifacts downloaded from the model registry microservice by DL Streamer Pipeline Server.

**Usage**:
```bash
./int_mr_dir.sh
```
