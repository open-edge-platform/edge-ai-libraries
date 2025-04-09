#!/bin/bash

# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials, 
# and your use of them is governed by the express license under which they 
# were provided to you ("License"). Unless the License provides otherwise, 
# you may not use, modify, copy, publish, distribute, disclose or transmit 
# this software or the related documents without Intel's prior written 
# permission. 
#
# This software and the related documents are provided as is, with no express 
# or implied warranties, other than those that are expressly stated in the License.

# start: ./generate_ssl_files.sh

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SETUP_DIR=$SCRIPT_DIR/Certificates
SETUP_SSL_DIR=$SETUP_DIR/ssl
SETUP_SSL_EXP="365"
PROJECT_DIR_NAME=$(basename "$SCRIPT_DIR")
PROJECT_DIR_NAME_LC=$(echo "$PROJECT_DIR_NAME" | tr '[:upper:]' '[:lower:]')
MR_UID=$(awk -F= '$1 == "MR_UID" {print $2}' ../docker/.env)
MR_MINIO_HOSTNAME=$(awk -F= '$1 == "MR_MINIO_HOSTNAME" {print $2}' ../docker/.env)

set -e

createSSLCAKeyCert () {
  echo "Creating CA certificate and key..."

  # create CA key
  openssl genrsa -out $SETUP_SSL_DIR/$1-ca.key 4096 >/dev/null 2>&1

  # create CA CSR
  openssl req -new -key $SETUP_SSL_DIR/$1-ca.key \
              -out $SETUP_SSL_DIR/$1-ca.csr -sha512 \
              -subj "/O=$PROJECT_DIR_NAME_LC Corp/CN=${PROJECT_DIR_NAME_LC}_ca_cert"

  # create CA CNF
cat > $SETUP_SSL_DIR/$1-ca.cnf <<EOF
[root_ca]
basicConstraints = critical,CA:TRUE,pathlen:1
keyUsage = critical, nonRepudiation, cRLSign, keyCertSign
subjectKeyIdentifier=hash
EOF

  # create CA CRT (self-signed with CA key)
  openssl x509 -req -days $SETUP_SSL_EXP -sha512 \
                  -in $SETUP_SSL_DIR/$1-ca.csr \
                  -signkey $SETUP_SSL_DIR/$1-ca.key \
                  -out $SETUP_SSL_DIR/$1-ca.crt \
                  -extfile $SETUP_SSL_DIR/$1-ca.cnf \
                  -extensions root_ca >/dev/null 2>&1
}

createSSLKeyCert () {
  echo "Creating certificate and key for '$1'..."

  # create server key
  openssl genrsa -out $SETUP_SSL_DIR/$1.key 4096 >/dev/null 2>&1
  
  # create server CSR
  openssl req -new -sha512 \
              -key "$SETUP_SSL_DIR"/"$1".key \
              -out "$SETUP_SSL_DIR"/"$1".csr \
              -subj "/O=$PROJECT_DIR_NAME_LC Corp/CN=${PROJECT_DIR_NAME_LC}_cert"

  # create server CNF
  ALT_NAMES_LIST=("localhost" "$MR_MINIO_HOSTNAME")

  ALT_IPS_LIST=("127.0.0.1")

  if [[ "$2" != "" ]]; then
    ALT_IPS_LIST+=("${2}")
  fi 

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
  echo -e $ALT_NAMES >> $SETUP_SSL_DIR/$1.cnf

  # alternative ips
  ALT_IPS=""
  COUNT=1
  TOTAL_ALT_IPS_LIST=${#ALT_IPS_LIST[@]}
  for CURRENT_ALT_IP in "${ALT_IPS_LIST[@]}"
  do
  if [ "${COUNT}" == "${TOTAL_ALT_NAMES_LIST}" ]; then
    ALT_IPS="${ALT_IPS}IP.${COUNT} = $CURRENT_ALT_IP"
  else
    ALT_IPS="${ALT_IPS}IP.${COUNT} = $CURRENT_ALT_IP\n"
  fi
  COUNT=$((COUNT+1)) 
  done
  echo -e $ALT_IPS >> $SETUP_SSL_DIR/$1.cnf

  # create server CRT (signed with CA KEY & CRT)
  openssl x509 -req -days $SETUP_SSL_EXP -sha512 \
                    -in $SETUP_SSL_DIR/$1.csr \
                    -CA $SETUP_SSL_DIR/$1-ca.crt \
                    -CAkey $SETUP_SSL_DIR/$1-ca.key \
                    -CAcreateserial \
                    -out $SETUP_SSL_DIR/$1.crt \
                    -extfile $SETUP_SSL_DIR/$1.cnf \
                    -extensions $1 >/dev/null 2>&1
}

#!/bin/bash


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
  echo "Copied '$source_file' to '$dest_file/$new_filename'"
}



createSSLCertsAndKey() {
    # setup SSL Certs and Key
    if [[ ! -f "$SETUP_SSL_DIR/server.key" ]]; then
        echo "Initializing CA and Server certificates and keys creation"
        mkdir -p "${SETUP_SSL_DIR}"

        createSSLCAKeyCert "server"
        createSSLKeyCert "server" "$1"

        copy_and_rename "$SETUP_SSL_DIR/server.key" "$SETUP_SSL_DIR/private.key"
        copy_and_rename "$SETUP_SSL_DIR/server.crt" "$SETUP_SSL_DIR/public.crt"

        sudo chown -R "$MR_UID" "$SETUP_SSL_DIR"
    else
        echo "Certificates and Keys for Certificate Authority and Server already exist."
    fi
}

# Function to display a Help message
print_help() {
    echo "Usage: $0 [server_ip]"
    echo ""
    echo "Arguments:"
    echo "  [server_ip]                            (Optional) The IP address of the server to be included in the certificate"
    echo "                                         Required for ssl certificate verification by other machines communicating"
    echo "                                         with the server or application using the certificate."
    echo ""
    echo "Example:"
    echo "  ./generate_ssl_files.sh 192.168.1.100"
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
# If not provided, default to empty string
server_ip="${1:-}"

# Check if help message is requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  print_help
  exit 0
fi

# If the first argument (server_ip) is not "" and is not valid ip address format, print help message
if [[ "$server_ip" != "" && $(is_ip_address "$server_ip") == 1 ]]; then
    printf "Error: Invalid argument.\n\n"
    print_help
    exit 1
fi


createSSLCertsAndKey "$server_ip"
