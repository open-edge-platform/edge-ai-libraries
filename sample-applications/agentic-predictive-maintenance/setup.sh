#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m'

# =================== Defaults ======================
USE_CASE=""
CONFIG_ONLY=false

# =================== Functions ======================
show_help() {
    echo -e "Agentic Predictive Maintenance Blueprint v1.0"
    echo -e "Copyright (C) 2026 Intel Corporation"
    echo -e ""
    echo -e "${YELLOW}USAGE:${NC}"
    echo -e "  ${GREEN}source setup.sh --use-case <use-case-name> [--stop | --clean-data | config]${NC}"
    echo -e ""
    echo -e "${YELLOW}OPTIONS:${NC}"
    echo -e "  ${BLUE}--use-case <name>${NC}    Use case to deploy (required). Example: pipeline-defect-detection"
    echo -e "  ${BLUE}--stop${NC}               Bring down all running containers"
    echo -e "  ${BLUE}--clean-data${NC}         Bring down containers and remove all volumes"
    echo -e "  ${BLUE}config${NC}               Print resolved compose configuration without starting"
    echo -e "  ${BLUE}-h, --help${NC}           Show this help message"
    echo -e ""
    echo -e "${YELLOW}EXAMPLES:${NC}"
    echo -e "  ${GRAY}source setup.sh --use-case pipeline-defect-detection"
    echo -e "  source setup.sh --use-case weld-defect-detection"
    echo -e "  source setup.sh --use-case pipeline-defect-detection --stop${NC}"
}

stop_containers() {
    echo -e "${YELLOW}Bringing down all containers...${NC}"
    docker compose \
        -f docker/compose.base.yaml \
        -f docker/compose.agents.yaml \
        -f docker/compose.llm.yaml \
        -f docker/compose.ui.yaml \
        down
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to stop containers.${NC}" >&2
        return 1
    fi
    echo -e "${GREEN}All containers stopped and removed.${NC}"
}

remove_volumes() {
    echo -e "${YELLOW}Removing Docker volumes...${NC}"
    docker volume rm apm_sqlite_data apm_model_cache 2>/dev/null
    echo -e "${GREEN}Volumes removed.${NC}"
}

validate_env() {
    local env_file=".env_${USE_CASE}"
    if [ ! -f "${env_file}" ]; then
        echo -e "${RED}ERROR: Environment file '${env_file}' not found.${NC}" >&2
        echo -e "${YELLOW}Create it by copying the template for your use case.${NC}" >&2
        return 1
    fi

    # Source the env file
    set -a
    source "${env_file}"
    set +a

    # Validate required variables
    local required_vars=("HOST_IP" "LLM_MODEL_NAME" "LLM_DEVICE")
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo -e "${RED}ERROR: Required variable '${var}' is not set in ${env_file}.${NC}" >&2
            return 1
        fi
    done

    echo -e "${GREEN}Environment validated.${NC}"
    return 0
}

# =================== Argument Parsing ======================
if [ "$#" -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    return 0 2>/dev/null || exit 0
fi

ACTION="start"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --use-case)
            USE_CASE="$2"
            shift 2
            ;;
        --stop|--down)
            ACTION="stop"
            shift
            ;;
        --clean-data)
            ACTION="clean"
            shift
            ;;
        config)
            CONFIG_ONLY=true
            shift
            ;;
        *)
            echo -e "${RED}ERROR: Unknown argument '$1'${NC}" >&2
            show_help
            return 1 2>/dev/null || exit 1
            ;;
    esac
done

# =================== Validate use-case ======================
if [ "${ACTION}" != "stop" ] && [ "${ACTION}" != "clean" ] && [ -z "${USE_CASE}" ]; then
    echo -e "${RED}ERROR: --use-case is required.${NC}" >&2
    show_help
    return 1 2>/dev/null || exit 1
fi

# =================== Resolve use-case paths ======================
if [ -n "${USE_CASE}" ]; then
    # Look for the use-case in the current repo (eal) or sibling eas repo
    USE_CASE_DIR=""
    CANDIDATE_DIRS=(
        "${PWD}/apps/${USE_CASE}"
    )
    for dir in "${CANDIDATE_DIRS[@]}"; do
        if [ -d "${dir}" ]; then
            USE_CASE_DIR="${dir}"
            break
        fi
    done

    if [ -z "${USE_CASE_DIR}" ]; then
        echo -e "${RED}ERROR: Use case '${USE_CASE}' not found.${NC}" >&2
        echo -e "${YELLOW}Expected directory: apps/${USE_CASE}/${NC}" >&2
        return 1 2>/dev/null || exit 1
    fi
    export USE_CASE_DIR
    export USE_CASE
fi

# =================== Execute ======================
case "${ACTION}" in
    stop)
        stop_containers
        ;;
    clean)
        stop_containers && remove_volumes
        ;;
    start)
        validate_env || { return 1 2>/dev/null || exit 1; }

        export APP_HOST_PORT="${APP_HOST_PORT:-8080}"
        export USE_CASE_CONFIGS_DIR="${USE_CASE_DIR}/configs"
        export USE_CASE_PROMPTS_DIR="${USE_CASE_DIR}/prompts"
        export USE_CASE_MODELS_DIR="${USE_CASE_DIR}/models"

        echo -e "${BLUE}Starting Agentic Predictive Maintenance — use case: ${USE_CASE}${NC}"

        COMPOSE_CMD="docker compose \
            -f docker/compose.base.yaml \
            -f docker/compose.agents.yaml \
            -f docker/compose.llm.yaml \
            -f docker/compose.ui.yaml"

        if [ "${CONFIG_ONLY}" = true ]; then
            ${COMPOSE_CMD} config
        else
            ${COMPOSE_CMD} up -d
            if [ $? -ne 0 ]; then
                echo -e "${RED}ERROR: Failed to start containers.${NC}" >&2
                return 1 2>/dev/null || exit 1
            fi
            echo -e "${GREEN}Application started. UI available at: http://${HOST_IP}:${APP_HOST_PORT}${NC}"
        fi
        ;;
esac
