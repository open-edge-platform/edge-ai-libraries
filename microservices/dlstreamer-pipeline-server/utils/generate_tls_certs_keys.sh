#!/bin/bash

#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

# start: ./generate_tls_certs_keys.sh

script_full_filename=$(basename "$0")

# Check if the script is being executed from the script's directory
if [[ "$0" != "./$script_full_filename" ]]; then
    echo "Error: This script must be executed from the script's directory."
    exit 1
fi

CURR_WORKING_DIR=$(pwd)
PARENT_DIR=$(dirname "$CURR_WORKING_DIR")
SETUP_DIR=$PARENT_DIR/Certificates
SETUP_SSL_DIR=$SETUP_DIR/ssl_server
SETUP_SSL_EXP="365"
PROJECT_DIR_SERVICE_NAME=${PARENT_DIR##*/}

if [[ $PROJECT_DIR_SERVICE_NAME =~ \..*  ]]; then
  PROJECT_DIR_SERVICE_NAME=${PROJECT_DIR_SERVICE_NAME##*.}
fi

PROJECT_DIR_NAME_LC=$(echo "$PROJECT_DIR_SERVICE_NAME" | tr '[:upper:]' '[:lower:]')
PIPELINE_SERVER_UID=$(awk -F= '$1 == "UID" {print $2}' ../docker/.env)

ALT_IPS_LIST=(
  "127.0.0.1"
)

set -e

# Function to create a certificate and key for the CA
create_ssl_ca_key_cert () {
  printf "\nCreating CA certificate and private key...\n"

  # create CA private key
  openssl genrsa -out "$SETUP_SSL_DIR"/ca.key 4096 >/dev/null 2>&1

  # create CA CSR
  openssl req -new -key "$SETUP_SSL_DIR"/ca.key \
              -out "$SETUP_SSL_DIR"/ca.csr -sha512 \
              -subj "/O=$PROJECT_DIR_NAME_LC Corp/CN=${PROJECT_DIR_NAME_LC}_ca_cert"

  # create CA CNF
cat > "$SETUP_SSL_DIR"/ca.cnf <<EOF
[root_ca]
basicConstraints = critical,CA:TRUE,pathlen:1
keyUsage = critical, nonRepudiation, cRLSign, keyCertSign
subjectKeyIdentifier=hash
EOF

  # create CA CRT (self-signed with CA key)
  openssl x509 -req -days $SETUP_SSL_EXP -sha512 \
                  -in "$SETUP_SSL_DIR"/ca.csr \
                  -signkey "$SETUP_SSL_DIR"/ca.key \
                  -out "$SETUP_SSL_DIR"/ca.crt \
                  -extfile "$SETUP_SSL_DIR"/ca.cnf \
                  -extensions root_ca >/dev/null 2>&1

  printf "CA certificate, private key and configuration files created.\n\n"
}

# Function to create a certificate and key
create_ssl_key_cert () {
  echo "Creating SSL certificate and private key for '$1'"

  # create key
  openssl genrsa -out "$SETUP_SSL_DIR"/"$1".key 4096 >/dev/null 2>&1

  if [[ "$1" == "server" && "$1" == "" ]]; then
    COMMON_NAME="$PROJECT_DIR_NAME_LC"
  elif [ "$1" == "client" ]; then
    COMMON_NAME="client"
  fi

  # create CSR
  openssl req -new -sha512 \
              -key "$SETUP_SSL_DIR"/"$1".key \
              -out "$SETUP_SSL_DIR"/"$1".csr \
              -subj "/O=$PROJECT_DIR_NAME_LC Corp/CN=${COMMON_NAME}_cert"

  # create CNF
  ALT_NAMES_LIST=("localhost")

cat > "$SETUP_SSL_DIR"/"$1".cnf <<EOF
[$1]
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names
[alt_names]
EOF

  # alternative names
  ALT_NAMES=""
  COUNT=1
  TOTAL_ALT_NAMES_LIST=${#ALT_NAMES_LIST[@]}
  for CURRENT_ALT_NAME in "${ALT_NAMES_LIST[@]}"
  do
  if [ "${COUNT}" == "${TOTAL_ALT_NAMES_LIST}" ]; then
    ALT_NAMES="${ALT_NAMES}DNS.${COUNT} = $CURRENT_ALT_NAME"
  else
    ALT_NAMES="${ALT_NAMES}DNS.${COUNT} = $CURRENT_ALT_NAME\n"
  fi
  COUNT=$((COUNT+1)) 
  done
  echo -e "$ALT_NAMES" >> "$SETUP_SSL_DIR"/"$1".cnf

  # alternative ips
  ALT_IPS=""
  COUNT=1
  TOTAL_ALT_IPS_LIST=${#ALT_IPS_LIST[@]}
  
  for CURRENT_ALT_IP in "${ALT_IPS_LIST[@]}"
  do
  if [ "${COUNT}" == "${TOTAL_ALT_IPS_LIST}" ]; then
    ALT_IPS="${ALT_IPS}IP.${COUNT} = $CURRENT_ALT_IP"
  else
    ALT_IPS="${ALT_IPS}IP.${COUNT} = $CURRENT_ALT_IP\n"
  fi
  COUNT=$((COUNT+1)) 
  done
  echo -e "$ALT_IPS" >> "$SETUP_SSL_DIR"/"$1".cnf

  # create CRT (signed with CA KEY & CRT)
  openssl x509 -req -days $SETUP_SSL_EXP -sha512 \
                    -in "$SETUP_SSL_DIR"/"$1".csr \
                    -CA "$SETUP_SSL_DIR"/ca.crt \
                    -CAkey "$SETUP_SSL_DIR"/ca.key \
                    -CAcreateserial \
                    -out "$SETUP_SSL_DIR"/"$1".crt \
                    -extfile "$SETUP_SSL_DIR"/"$1".cnf \
                    -extensions "$1" >/dev/null 2>&1

  printf "%s certificate, private key and configuration files created.\n\n" "$1"
}

# Function to create a copy of a file and rename it
copy_and_rename() {
  # Check if two arguments are provided
  if [ $# -ne 2 ]; then
    echo "Error: Please provide two file names as arguments."
    return 1
  fi

  # source and destination file names
  source_file="$1"
  dest_file="$2"

  if [ ! -f "$source_file" ]; then
    echo "Error: Source file '$source_file' does not exist."
    return 1
  fi

  # Copy the file with the new name
  cp "$source_file" "$dest_file"

  # Print success message
  source_file="$(basename "$source_file")"
  dest_file="$(basename "$dest_file")"

  echo "Copied '$source_file' to '$dest_file'"
}


# Function to initate certificates and keys creation
create_ssl_certs_and_keys() {
    echo "Initializing certificates and keys creation..."
    
    mkdir -p "${SETUP_SSL_DIR}"

    # setup SSL Certs and Key
    if [[ ! -f "$SETUP_SSL_DIR/server.key" ]]; then
        create_ssl_ca_key_cert

        if [[ "$2" != "" ]]; then
          ALT_IPS_LIST+=("${2}")
        fi 

        create_ssl_key_cert "server" "$2"
        
        # Create the client's files if $2 is "client"
        if [[ "$1" == "true" ]]; then
          create_ssl_key_cert "client" "$2"
        fi

        copy_and_rename "$SETUP_SSL_DIR/server.key" "$SETUP_SSL_DIR/private.key"
        copy_and_rename "$SETUP_SSL_DIR/server.crt" "$SETUP_SSL_DIR/public.crt"

        sudo chown -R "$PIPELINE_SERVER_UID" "$SETUP_SSL_DIR"
    else
      echo "Certificates and keys already exists."
    fi
}

# Function to display a Help message
print_help() {
    echo "Usage: $0 [create_client_cert_key_flag] [server_ip]"
    echo ""
    echo "Arguments:"
    echo "  [create_client_cert_key_flag]        (Optional) A flag to indicate whether to generate a certificate and"
    echo "                                         private key for a client. Default is false."
    echo "  [server_ip]                            (Optional) The IP address of the server to be included in the client's"
    echo "                                         certificate. Required if create_client_cert_key_flag is true"
    echo "                                         and the client is hosted on a separate system."
    echo ""
    echo "Example:"
    echo "  ./generate_tls_certs_keys.sh true 192.168.1.100"
}

# Function to join elements in a list with commas
join_elements() {
  local joined_string=""
  local separator=""
  for element in "$@"; do
    joined_string="$joined_string$separator$element"
    separator=","
  done
  echo "$joined_string"
}

# Function to validate whether the provided string is an IP address
is_ip_address() {
  local ip="$1"
  local regex="^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"

  if [[ "$ip" =~ $regex ]]; then
    echo 0
    return 0
  else
    echo 1
    return 1
  fi
}

# Get script arguments
create_client_cert_key="${1:-false}"
server_ip="${2:-}"

# Check if help message is requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  print_help
  exit 0
fi

# If the first argument is not "true" and "false", print help message
if [[ $create_client_cert_key != "true" && $create_client_cert_key != "false" ]]; then
    printf "Error: Invalid create_client_cert_key_flag value.\n\n"
    print_help
    exit 1
fi

# If the first argument is "true" and server_ip is "", print help message
if [[ $create_client_cert_key == "true"  && -z "$server_ip" ]]; then
    ips=$(join_elements "${ALT_IPS_LIST[@]}")
    echo "Note: The client's certificate will only be identified by the IP address $ips."
elif [[ $create_client_cert_key == "true" && $(is_ip_address "$server_ip") == 1 ]]; then
    printf "Error: server_ip is not a valid IP address.\n\n"
    print_help
    exit 1
fi

echo "Service Name: $PROJECT_DIR_SERVICE_NAME"
create_ssl_certs_and_keys "$create_client_cert_key" "$server_ip"

