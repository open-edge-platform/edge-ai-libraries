#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/../.." && pwd)
API_SPEC=${API_SPEC:-"$PROJECT_DIR/docs/user-guide/_assets/openapi.yaml"}
RESTLER_BIN=${RESTLER_BIN:-Restler}
TARGET_IP=${TARGET_IP:-localhost}
TARGET_PORT=${TARGET_PORT:-8192}
FUZZ_MODE=${FUZZ_MODE:-test}
FUZZ_TIME_BUDGET_MINUTES=${FUZZ_TIME_BUDGET_MINUTES:-1}
RESTLER_OUTPUT_DIR=${RESTLER_OUTPUT_DIR:-"$SCRIPT_DIR/restler_output"}
RESTLER_OUTPUT_DIR=$(cd -- "$(dirname -- "$RESTLER_OUTPUT_DIR")" && pwd)/$(basename -- "$RESTLER_OUTPUT_DIR")

case "$FUZZ_MODE" in
  test)
    RESULT_DIR_NAME=Test
    ;;
  fuzz-lean)
    RESULT_DIR_NAME=FuzzLean
    ;;
    *)
        printf 'FUZZ_MODE must be "test" or "fuzz-lean", got: %s\n' "$FUZZ_MODE" >&2
        exit 2
        ;;
esac

if ! command -v "$RESTLER_BIN" >/dev/null 2>&1; then
    printf 'RESTler executable not found: %s\n' "$RESTLER_BIN" >&2
    printf 'Set RESTLER_BIN or add the RESTler binary directory to PATH.\n' >&2
    exit 127
fi

if [[ ! -f "$API_SPEC" ]]; then
    printf 'OpenAPI specification not found: %s\n' "$API_SPEC" >&2
    exit 2
fi

mkdir -p "$RESTLER_OUTPUT_DIR"
COMPILE_DIR="$RESTLER_OUTPUT_DIR/Compile"
DICTIONARY_FILE="$RESTLER_OUTPUT_DIR/dict.json"

cat > "$DICTIONARY_FILE" <<'EOF'
{
  "restler_fuzzable_string": [
    "",
    "not_a_url",
    "../../../../etc/passwd",
    "file:///etc/passwd",
    "http://127.0.0.1:2375/containers/json",
    "https://example.invalid/video.mp4",
    "'; DROP TABLE summaries; --",
    "<script>alert(1)</script>",
    "line1\nforged-log-entry"
  ],
  "restler_fuzzable_int": [
    "-1",
    "0",
    "1",
    "2147483647"
  ],
  "restler_fuzzable_number": [
    "-1",
    "0",
    "0.000001",
    "1000000"
  ],
  "restler_custom_payload": {
    "/v1/tasks/post/__body__": [
      "{\"task_name\":\"restler_fuzz_task\",\"mode\":\"full\",\"content\":{\"text\":\"GLOBAL_PROMPT='''Summarize the events. {question}'''\\n\\nLOCAL_PROMPT='''Describe the clip from {st_tm} to {end_tm}.'''\"}}"
    ],
    "/v1/tasks/{name}/patch/__body__": [
      "{\"description\":\"Updated by RESTler fuzz testing\"}"
    ]
  }
}
EOF

rm -rf "$COMPILE_DIR"
COMPILER_CONFIG="$RESTLER_OUTPUT_DIR/restler_compile_config.json"
cat > "$COMPILER_CONFIG" <<EOF
{
  "SwaggerSpecFilePath": ["$API_SPEC"],
  "GrammarOutputDirectoryPath": "$COMPILE_DIR",
  "CustomDictionaryFilePath": "$DICTIONARY_FILE",
  "IncludeOptionalParameters": true,
  "UseBodyExamples": true,
  "ResolveBodyDependencies": true
}
EOF
(
    cd "$RESTLER_OUTPUT_DIR"
  "$RESTLER_BIN" compile "$COMPILER_CONFIG"
)

if [[ ! -f "$COMPILE_DIR/grammar.py" || ! -f "$COMPILE_DIR/engine_settings.json" ]]; then
    printf 'RESTler compilation did not create the expected grammar files.\n' >&2
    exit 1
fi

VALUE_GENERATORS_FILE="$SCRIPT_DIR/task_value_generators.py"
sed -i "1s|{|{\n  \"custom_value_generators\": \"$VALUE_GENERATORS_FILE\",\n  \"per_resource_settings\": {\n    \"/v1/tasks\": {\"create_once\": 1}\n  },|" \
  "$COMPILE_DIR/engine_settings.json"

"$RESTLER_BIN" --workingDirPath "$RESTLER_OUTPUT_DIR" "$FUZZ_MODE" \
    --grammar_file "$COMPILE_DIR/grammar.py" \
    --dictionary_file "$DICTIONARY_FILE" \
    --settings "$COMPILE_DIR/engine_settings.json" \
    --target_ip "$TARGET_IP" \
    --target_port "$TARGET_PORT" \
    --no_ssl \
    --time_budget "$FUZZ_TIME_BUDGET_MINUTES"

printf 'RESTler %s completed. Compiler artifacts are under %s/Compile and runtime results are under %s/%s.\n' \
  "$FUZZ_MODE" "$RESTLER_OUTPUT_DIR" "$RESTLER_OUTPUT_DIR" "$RESULT_DIR_NAME"