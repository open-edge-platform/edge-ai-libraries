#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Make's subprocess entry point. The shared sourced implementation deliberately
# uses explicit return-code handling rather than errexit/nounset.
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

init_env() {
    if [ ! -e "${ENV_FILE:-.env}" ]; then
        (umask 077; set -C; cat .env.example > "${ENV_FILE:-.env}") || return 1
        echo "Created ${ENV_FILE:-.env}; export service credentials before deploying." >&2
    fi
}

load_env() {
    local file="${ENV_FILE:-.env}" line key value number=0
    if [ ! -f "$file" ]; then
        echo "ERROR: Environment file not found: $file. Run make init-env first." >&2
        return 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        number=$((number + 1))
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
        if [[ ! "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([a-zA-Z_][a-zA-Z0-9_]*)[[:space:]]*=(.*)$ ]]; then
            echo "ERROR: Invalid environment assignment at $file:$number." >&2
            return 1
        fi
        key="${BASH_REMATCH[2]}"
        value="${BASH_REMATCH[3]}"
        value="${value#"${value%%[![:space:]]*}"}"
        if [[ "$value" =~ ^\"(.*)\"[[:space:]]*(#.*)?$ ]] ||
           [[ "$value" =~ ^\'(.*)\'[[:space:]]*(#.*)?$ ]]; then
            value="${BASH_REMATCH[1]}"
        elif [[ "$value" == \"* || "$value" == \'* ]]; then
            echo "ERROR: Unclosed quoted value at $file:$number." >&2
            return 1
        else
            value="${value%%[[:space:]]#*}"
            value="${value%"${value##*[![:space:]]}"}"
        fi
        if [[ -v "$key" ]]; then
            export "$key=${!key}" || return 1
        elif [ -n "$value" ]; then
            export "$key=$value" || return 1
        fi
    done < "$file"
    export COMPOSE_ENV_FILES="$file"
}

docker_preflight() {
    if ! timeout 15 docker info >/dev/null 2>&1; then
        echo "ERROR: Docker is unavailable or its daemon is not reachable." >&2
        return 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        echo "ERROR: Docker Compose v2 is required." >&2
        return 1
    fi
}

wait_for_health() {
    local base="http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}"
    local timeout="${HEALTH_TIMEOUT:-300}" deadline
    if [[ ! "$timeout" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: HEALTH_TIMEOUT must be a positive integer in seconds." >&2
        return 1
    fi
    deadline=$((SECONDS + timeout))
    until curl -sf --max-time 5 "$base/manager/health" >/dev/null; do
        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "ERROR: VSS health check timed out: $base/manager/health" >&2
            return 1
        fi
        sleep 5
    done
    echo "Pipeline Manager is healthy: $base/manager/health"
    echo "API documentation: $base/manager/docs"
}

main() {
    local action="${1:-}" mode="${2:-}"
    case "$action" in
        init-env) init_env; return $? ;;
        deploy|config)
            [ "$action" = config ] && mode="${mode:-dual}"
            case "$mode" in
                summary|search|dual|unified) ;;
                *)
                    echo "ERROR: Specify MODE=summary, search, dual, or unified." >&2
                    return 1
                    ;;
            esac
            ;;
        stop|clean-data|mcp|stop-mcp|setenv|health-check) ;;
        *) echo "ERROR: Unknown VSS operation: $action" >&2; return 1 ;;
    esac

    case "$action" in
        stop|clean-data|stop-mcp)
            docker_preflight || return 1
            # Teardown must also work before any environment file is created.
            if [ -f "${ENV_FILE:-.env}" ] || [ -n "${ENV_FILE:-}" ]; then
                load_env || return 1
            fi
            source ./setup.sh "--$action"
            return $?
            ;;
    esac

    # Record only application exports, not unrelated inherited shell secrets.
    if [ "$action" = setenv ]; then
        declare -A application_exports=()
        export() {
            # Forward export assignments unchanged while tracking their names.
            # shellcheck disable=SC2163
            builtin export "$@" || return 1
            local assignment
            for assignment in "$@"; do
                application_exports["${assignment%%=*}"]=1
            done
        }
    fi

    if [ "${ENV_FILE:-.env}" = .env ]; then
        init_env || return 1
    fi
    load_env || return 1

    case "$action" in
        deploy|mcp) docker_preflight || return 1 ;;
    esac
    case "$action" in
        deploy) source ./setup.sh "--$mode" ;;
        config) source ./setup.sh "--$mode" config ;;
        mcp)
            export HOST_IP="${HOST_IP:-$(ip route get 1 | awk '{print $7}')}"
            source ./setup.sh --mcp
            ;;
        health-check) wait_for_health ;;
        setenv)
            source ./setup.sh --setenv >&2 || return 1
            unset -f export
            local name
            for name in "${!application_exports[@]}"; do
                printf 'export %s=%q\n' "$name" "${!name}"
            done
            ;;
    esac
}

main "$@"
