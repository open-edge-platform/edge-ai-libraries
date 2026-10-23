#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Offline regression tests: no real Docker/OpenShell operations or external network.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for lib in colors state agents openshell; do
  # shellcheck disable=SC1090
  . "$SCRIPT_DIR/scripts/lib/$lib.sh"
done
. "$SCRIPT_DIR/test/openshell-test-lib.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -f -- "$TEST_LOG"; rm -rf -- "$TEST_ROOT"' EXIT
export HOME="$TEST_ROOT/home"
mkdir -p "$HOME"
export NO_COLOR=1
export NON_INTERACTIVE=1
HARNESS_AGENT=openclaw
HARNESS_RUNTIME=openshell
OPENSHELL_NAME=ahi-0123456789ab
OPENSHELL_GATEWAY=openshell
OPENSHELL_OWNER=0123456789abcdef0123456789abcdef
HARNESS_IR_PORT=8010
HARNESS_IR_CONTAINER=ir
HARNESS_LLM_MODEL=test-model

startup_fixture() {
  local fixture
  fixture="$(mktemp -d "$TEST_ROOT/startup.XXXXXX")"
  export HOME="$fixture/home"
  export REAL_NODE
  REAL_NODE="$(command -v node)"
  mkdir -p "$HOME" "$fixture/bin"
  export HARNESS_AGENT=openclaw
  export HARNESS_SANDBOX_ENDPOINT=http://host.openshell.internal:8010/v1
  export HARNESS_SANDBOX_MODEL=test-model
  export HARNESS_MODEL_CONFIG_SCRIPT="$SCRIPT_DIR/openshell/model-config.mjs"
  cat >"$fixture/bin/node" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "$SQLITE_TMPDIR" == "$HOME/.openclaw/tmp/sqlite" ]]
[[ -d "$SQLITE_TMPDIR" && -w "$SQLITE_TMPDIR" ]]
[[ "$(stat -c %a "$SQLITE_TMPDIR")" == 700 ]]
exec "$REAL_NODE" "$@"
SH
  cat >"$fixture/bin/openclaw" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == "gateway run" ]]
node <<'JS'
const assert = require("node:assert/strict");
const {DatabaseSync} = require("node:sqlite");
const db = new DatabaseSync(`${process.env.HOME}/.openclaw/startup-test.sqlite`);
try {
  db.exec("BEGIN IMMEDIATE");
  db.exec("CREATE VIRTUAL TABLE IF NOT EXISTS startup_fts USING fts5(content)");
  if (!db.prepare("SELECT rowid FROM startup_fts WHERE rowid = 1").get())
    db.prepare("INSERT INTO startup_fts(rowid, content) VALUES (1, ?)").run("persistent conversation");
  assert.equal(db.prepare("SELECT content FROM startup_fts WHERE startup_fts MATCH ?").get("persistent").content,
    "persistent conversation");
  db.exec("COMMIT");
} finally {
  db.close();
}
JS
SH
  chmod 755 "$fixture/bin/node" "$fixture/bin/openclaw"
  export PATH="$fixture/bin:$PATH"
}
startup_fresh() {
  startup_fixture
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  [[ -f "$HOME/.openclaw/openclaw.json" ]]
  [[ -f "$HOME/.openclaw/startup-test.sqlite" ]]
}
startup_inherited_temp() {
  startup_fixture
  export SQLITE_TMPDIR="$HOME/nonexistent-inherited-temp"
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  [[ ! -e "$SQLITE_TMPDIR" ]]
}
startup_private_temp() {
  startup_fixture
  mkdir -p "$HOME/.openclaw/tmp/sqlite"
  chmod 755 "$HOME/.openclaw/tmp/sqlite"
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  [[ "$(stat -c %a "$HOME/.openclaw/tmp/sqlite")" == 700 ]]
}
startup_restart() {
  startup_fixture
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  cp "$HOME/.openclaw/openclaw.json" "$HOME/config-before.json"
  printf 'preserved history\n' >"$HOME/.openclaw/history-marker"
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  cmp "$HOME/config-before.json" "$HOME/.openclaw/openclaw.json"
  [[ "$(cat "$HOME/.openclaw/history-marker")" == 'preserved history' ]]
}
startup_model_switch() {
  startup_fixture
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  token_before="$("$REAL_NODE" -e 'console.log(require(process.argv[1]).gateway.auth.token)' "$HOME/.openclaw/openclaw.json")"
  printf 'preserved history\n' >"$HOME/.openclaw/history-marker"
  "$REAL_NODE" "$HARNESS_MODEL_CONFIG_SCRIPT" openclaw changed-model "$HARNESS_SANDBOX_ENDPOINT"
  # The immutable creation environment still names test-model.
  [[ "$HARNESS_SANDBOX_MODEL" == test-model ]]
  bash "$SCRIPT_DIR/openshell/agent-start.sh"
  "$REAL_NODE" - "$HOME/.openclaw/openclaw.json" "$token_before" <<'JS'
const assert = require("node:assert/strict"), fs = require("node:fs");
const c = JSON.parse(fs.readFileSync(process.argv[2]));
assert.equal(c.models.providers.ovms.models[0].id, "changed-model");
assert.equal(c.agents.defaults.model.primary, "ovms/changed-model");
assert.equal(c.gateway.auth.token, process.argv[3]);
JS
  [[ "$(cat "$HOME/.openclaw/history-marker")" == 'preserved history' ]]
}
startup_blocked_temp() {
  startup_fixture
  mkdir -p "$HOME/.openclaw/tmp"
  printf 'not a directory\n' >"$HOME/.openclaw/tmp/sqlite"
  expect_failure 'mkdir.*sqlite' bash "$SCRIPT_DIR/openshell/agent-start.sh"
  [[ ! -e "$HOME/.openclaw/openclaw.json" ]]
  [[ ! -e "$HOME/.openclaw/startup-test.sqlite" ]]
}
startup_permissions_failure() {
  startup_fixture
  cat >"$(dirname "$(command -v node)")/chmod" <<'SH'
#!/usr/bin/env bash
printf 'SQLite temp permissions denied\n' >&2
exit 1
SH
  chmod 755 "$(dirname "$(command -v node)")/chmod"
  expect_failure 'SQLite temp permissions denied' bash "$SCRIPT_DIR/openshell/agent-start.sh"
  [[ ! -e "$HOME/.openclaw/openclaw.json" ]]
  [[ ! -e "$HOME/.openclaw/startup-test.sqlite" ]]
}

runtime_default() {
  HARNESS_RUNTIME=""
  select_runtime
  [[ "$HARNESS_RUNTIME" == host ]]
}
runtime_supported() {
  HARNESS_RUNTIME="$1"
  HARNESS_AGENT="$2"
  validate_runtime
}
profile_paths() {
  HARNESS_AGENT=openclaw
  local first
  first="$(openshell_profile_dir)"
  HARNESS_AGENT=hermes
  [[ "$first" != "$(openshell_profile_dir)" ]]
  [[ "$first" == "$HOME/$HARNESS_STATE_DIRNAME/openshell/openclaw" ]]
}
write_profile() {
  local dir
  dir="$(openshell_profile_dir)"
  mkdir -p "$dir"
  printf '%s\n' "$1" >"$dir/profile.json"
}
valid_profile='{"owner":"0123456789abcdef0123456789abcdef","name":"ahi-0123456789ab","gateway":"openshell","agent":"openclaw","model":"test-model"}'
profile_valid() {
  write_profile "$valid_profile"
  openshell_load_profile
  [[ "$OPENSHELL_MODEL" == test-model && "$OPENSHELL_NAME" == ahi-0123456789ab ]]
}
profile_invalid() {
  write_profile "$1"
  expect_failure 'Could not read the OpenShell ownership profile' openshell_load_profile
}
profile_missing() {
  expect_failure 'No OpenShell profile' openshell_load_profile
}
profile_symlink() {
  local dir
  dir="$(openshell_profile_dir)"
  mkdir -p "$dir"
  printf '%s' "$valid_profile" >"$TEST_ROOT/target.json"
  ln -s "$TEST_ROOT/target.json" "$dir/profile.json"
  expect_failure '[Ss]ymlink' openshell_load_profile
}
owned() {
  openshell() { printf '{"labels":{"agent-harness.owner":"0123456789abcdef0123456789abcdef"}}'; }
  openshell_assert_owned
}
unowned() {
  openshell() { printf '{"labels":{"agent-harness.owner":"someone-else"}}'; }
  expect_failure 'unowned sandbox' openshell_assert_owned
}
unavailable() {
  openshell() { return 1; }
  expect_failure 'Cannot inspect sandbox' openshell_assert_owned
}
resource_case() {
  local kind="$1" data="$2" expectation="$3"
  openshell() { printf '%s' "$data"; }
  if [[ "$expectation" == present ]]; then
    openshell_resource_exists "$kind"
  elif [[ "$expectation" == absent ]]; then
    if openshell_resource_exists "$kind"; then return 1; fi
  else
    expect_failure 'Invalid OpenShell resource response' openshell_resource_exists "$kind"
  fi
}
resource_unavailable() {
  openshell() { return 1; }
  expect_failure 'Cannot list OpenShell' openshell_resource_exists sandbox
}
version_case() {
  local version="$1"
  openshell() { printf 'openshell %s' "$version"; }
  if [[ "$version" == 0.1.5 ]]; then
    ensure_openshell_cli
  else
    expect_failure 'refusing to replace' ensure_openshell_cli
  fi
}
resolve_bind_host() { printf '127.0.0.1'; }
docker() {
  printf '{"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":"%s"}]}' "$HARNESS_IR_PORT"
}
invalid_bind() {
  resolve_bind_host() { printf '0.0.0.0'; }
  expect_failure 'must not be LAN-published' openshell_validate_shared_inference
}
invalid_port() {
  HARNESS_IR_PORT="$1"
  expect_failure 'must be between 1 and 65535' openshell_validate_shared_inference
}
invalid_publication() {
  local binding="$1"
  docker() { printf '%s' "$binding"; }
  expect_failure 'Refusing non-loopback or mismatched' openshell_validate_shared_inference
}
missing_ir() {
  docker() { return 1; }
  expect_failure 'Shared IR container is not available' openshell_validate_shared_inference
}
model_response() {
  local code="$1" response="$2" expected="$3"
  node - "$TEST_ROOT/port" "$code" "$response" <<'JS' &
const fs = require("node:fs");
const http = require("node:http");
const [file, status, response] = process.argv.slice(2);
const server = http.createServer((req, res) => {
  if (req.url !== "/v1/models") { res.writeHead(404); res.end(); return; }
  res.writeHead(Number(status), {"content-type": "application/json"});
  res.end(response);
});
server.listen(0, "127.0.0.1", () => fs.writeFileSync(file, String(server.address().port)));
JS
  MODEL_SERVER_PID=$!
  trap 'kill "$MODEL_SERVER_PID"; wait "$MODEL_SERVER_PID" 2>/dev/null || true; rm -f "$TEST_ROOT/port"' EXIT
  local attempt
  for attempt in {1..100}; do
    [[ ! -s "$TEST_ROOT/port" ]] || break
    sleep 0.05
  done
  [[ -s "$TEST_ROOT/port" ]]
  HARNESS_IR_PORT="$(cat "$TEST_ROOT/port")"
  if [[ "$expected" == pass ]]; then
    openshell_validate_shared_inference
  else
    expect_failure 'Shared inference is unavailable' openshell_validate_shared_inference
  fi
}
mock_lifecycle() {
  write_profile "$valid_profile"
  rm -f -- "$(openshell_profile_dir)/removed-profile.json"
  MOCK_SANDBOX_PRESENT=1
  MOCK_PROVIDER_PRESENT=1
  MOCK_OWNER="$OPENSHELL_OWNER"
  MOCK_DELETE_STALL=0
  MOCK_PROFILE_PRESENT=1
  MOCK_PROFILE_DELETE_FAIL=0
  : >"$TEST_ROOT/actions"
  openshell() {
    case "$1 $2" in
      'sandbox get') printf '{"labels":{"agent-harness.owner":"%s"}}' "$MOCK_OWNER" ;;
      'sandbox list')
        if [[ "$MOCK_SANDBOX_PRESENT" == 1 ]]; then
          printf '{"sandboxes":[{"name":"%s"}]}' "$OPENSHELL_NAME"
        else
          printf '{"sandboxes":[]}'
        fi ;;
      'provider list')
        if [[ "$MOCK_PROVIDER_PRESENT" == 1 ]]; then
          printf '{"providers":[{"name":"%s"}]}' "$OPENSHELL_NAME"
        else
          printf '{"providers":[]}'
        fi ;;
      'profile list')
        if [[ "$MOCK_PROFILE_PRESENT" == 1 ]]; then
          printf '[{"name":"%s","type":"provider"}]' "$OPENSHELL_NAME"
        else
          printf '[]'
        fi ;;
      'sandbox delete')
        printf 'sandbox delete\n' >>"$TEST_ROOT/actions"
        [[ "$MOCK_DELETE_STALL" == 1 ]] || MOCK_SANDBOX_PRESENT=0 ;;
      'provider delete')
        printf 'provider delete\n' >>"$TEST_ROOT/actions"
        MOCK_PROVIDER_PRESENT=0 ;;
      'profile delete')
        printf 'profile delete\n' >>"$TEST_ROOT/actions"
        [[ "$MOCK_PROFILE_DELETE_FAIL" == 1 ]] && return 1
        MOCK_PROFILE_PRESENT=0 ;;
      *) printf 'Unexpected mocked CLI call: %s\n' "$*" >&2; return 1 ;;
    esac
  }
}
removal_success() {
  mock_lifecycle
  remove_openshell_agent
  [[ ! -f "$(openshell_profile_dir)/profile.json" ]]
  cmp <(printf '%s\n' "$valid_profile") "$(openshell_profile_dir)/removed-profile.json"
  cmp <(printf 'sandbox delete\nprovider delete\nprofile delete\n') "$TEST_ROOT/actions"
}
removal_unowned() {
  mock_lifecycle
  MOCK_OWNER=someone-else
  expect_failure 'unowned sandbox' remove_openshell_agent
  [[ ! -s "$TEST_ROOT/actions" ]]
  [[ -f "$(openshell_profile_dir)/profile.json" ]]
}
removal_pending() {
  mock_lifecycle
  MOCK_DELETE_STALL=1
  sleep() { :; }
  expect_failure 'cleanup is pending' remove_openshell_agent
  [[ -f "$(openshell_profile_dir)/profile.json" ]]
  cmp <(printf 'sandbox delete\n') "$TEST_ROOT/actions"
}
removal_deletes_orphaned_profile() {
  mock_lifecycle
  MOCK_PROVIDER_PRESENT=0
  remove_openshell_agent
  cmp <(printf 'sandbox delete\nprofile delete\n') "$TEST_ROOT/actions"
  [[ ! -f "$(openshell_profile_dir)/profile.json" ]]
  [[ -f "$(openshell_profile_dir)/removed-profile.json" ]]
}
removal_profile_failure_retains_identity_for_retry() {
  mock_lifecycle
  MOCK_PROVIDER_PRESENT=0
  MOCK_PROFILE_DELETE_FAIL=1
  expect_failure 'Could not delete OpenShell provider profile' remove_openshell_agent
  [[ -f "$(openshell_profile_dir)/profile.json" ]]
  [[ ! -e "$(openshell_profile_dir)/removed-profile.json" ]]
  MOCK_PROFILE_DELETE_FAIL=0
  remove_openshell_agent
  [[ ! -f "$(openshell_profile_dir)/profile.json" ]]
  [[ -f "$(openshell_profile_dir)/removed-profile.json" ]]
  [[ "$(grep -c '^profile delete$' "$TEST_ROOT/actions")" == 2 ]]
}
removal_uses_installation_lock() {
  mock_lifecycle
  with_state_lock() {
    [[ "$1" == "openshell-openclaw" ]]
    shift
    "$@"
  }
  remove_openshell_agent
  grep -Fxq 'sandbox delete' "$TEST_ROOT/actions"
  grep -Fxq 'profile delete' "$TEST_ROOT/actions"
}
runner_failure_propagation() {
  expect_failure 'not ok 1 - intentional failure' bash -c '
    set -euo pipefail
    source "$1/test/openshell-test-lib.sh"
    trap '\''rm -f "$TEST_LOG"'\'' EXIT
    fail_before_success() { false; printf "This must never run\n"; }
    run_case "intentional failure" fail_before_success
    finish_tests
  ' _ "$SCRIPT_DIR"
}

printf 'TAP version 13\n'
run_case 'OpenClaw startup exports private SQLite temp before Node and initializes FTS5' startup_fresh
run_case 'OpenClaw startup replaces an inherited SQLite temp path' startup_inherited_temp
run_case 'OpenClaw startup restricts an existing SQLite temp directory to mode 700' startup_private_temp
run_case 'OpenClaw restart preserves config token and database content' startup_restart
run_case 'OpenClaw model change survives startup with the original sandbox environment' startup_model_switch
run_case 'OpenClaw startup fails before Node when SQLite temp creation fails' startup_blocked_temp
run_case 'OpenClaw startup fails before Node when SQLite temp permissions cannot be secured' startup_permissions_failure
run_case 'runtime defaults to host noninteractively' runtime_default
run_case 'host runtime remains supported' runtime_supported host openclaw
run_case 'OpenClaw supports OpenShell' runtime_supported openshell openclaw
run_case 'Hermes supports OpenShell' runtime_supported openshell hermes
run_case 'unsupported agent rejected' expect_failure 'supports openclaw and hermes only' runtime_supported openshell deepagents-code
run_case 'invalid runtime rejected' expect_failure 'Unknown runtime' runtime_supported invalid openclaw
run_case 'agent profile paths are separate' profile_paths
run_case 'valid persisted profile loads' profile_valid
# Each test gets a subshell, but fixtures on disk must also be reset between cases.
rm -rf -- "$HOME/$HARNESS_STATE_DIRNAME"
run_case 'missing profile rejected' profile_missing
run_case 'symlinked profile rejected' profile_symlink
rm -rf -- "$HOME/$HARNESS_STATE_DIRNAME"
run_case 'malformed profile rejected' profile_invalid '{'
run_case 'wrong agent profile rejected' profile_invalid "${valid_profile/openclaw/hermes}"
run_case 'invalid owner profile rejected' profile_invalid "${valid_profile/0123456789abcdef0123456789abcdef/invalid}"
run_case 'newline in model rejected' profile_invalid "${valid_profile/test-model/test\\nmodel}"
run_case 'matching ownership accepted' owned
run_case 'mismatched ownership rejected' unowned
run_case 'unavailable gateway is not treated as owned' unavailable
run_case 'existing sandbox found' resource_case sandbox '{"sandboxes":[{"name":"ahi-0123456789ab"}]}' present
run_case 'absent sandbox returns false' resource_case sandbox '{"sandboxes":[]}' absent
run_case 'existing provider found' resource_case provider '{"providers":[{"name":"ahi-0123456789ab"}]}' present
run_case 'paginated response rejected' resource_case sandbox '{"sandboxes":[],"next_page_token":"more"}' invalid
run_case 'malformed resource JSON rejected' resource_case sandbox '{' invalid
run_case 'unexpected resource schema rejected' resource_case sandbox '{"providers":[]}' invalid
run_case 'list failure is not treated as absence' resource_unavailable
run_case 'pinned CLI version accepted' version_case 0.1.5
run_case 'different CLI version rejected' version_case 0.1.4
run_case 'LAN bind rejected' invalid_bind
for port in invalid 0 65536; do
  run_case "invalid IR port $port rejected" invalid_port "$port"
done
run_case 'LAN Docker publication rejected' invalid_publication '{"8000/tcp":[{"HostIp":"0.0.0.0","HostPort":"8010"}]}'
run_case 'extra IPv6 Docker publication rejected' invalid_publication '{"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":"8010"},{"HostIp":"::","HostPort":"8010"}]}'
run_case 'wrong Docker port rejected' invalid_publication '{"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":"8020"}]}'
run_case 'missing Docker publication rejected' invalid_publication '{}'
run_case 'missing IR container rejected' missing_ir
run_case 'served model accepted through HTTP API' model_response 200 '{"data":[{"id":"test-model"}]}' pass
run_case 'unserved model rejected through HTTP API' model_response 200 '{"data":[{"id":"another-model"}]}' fail
run_case 'HTTP failure rejected' model_response 503 '{"error":"unavailable"}' fail
run_case 'malformed model JSON rejected' model_response 200 '{' fail
run_case 'owned removal deletes in order and archives state' removal_success
run_case 'unowned removal performs no deletion' removal_unowned
run_case 'pending removal retains ownership and provider' removal_pending
run_case 'orphaned provider profile is removed when the provider is absent' removal_deletes_orphaned_profile
run_case 'profile deletion failure retains ownership record for retry' removal_profile_failure_retains_identity_for_retry
run_case 'sandbox removal uses the per-agent installation lock' removal_uses_installation_lock
run_case 'test runner propagates an intermediate assertion failure' runner_failure_propagation
run_case 'installer documents runtime' bash -c 'bash "$1/install.sh" --help | grep -q -- --runtime' _ "$SCRIPT_DIR"
run_case 'uninstaller documents runtime' bash -c 'bash "$1/uninstall.sh" --help | grep -q -- --runtime' _ "$SCRIPT_DIR"
run_case 'invalid runtime CLI fails before setup' expect_failure 'Unknown runtime' bash "$SCRIPT_DIR/install.sh" --runtime invalid --non-interactive
run_case 'host connect is rejected' expect_failure 'connect.*openshell|OpenShell' bash "$SCRIPT_DIR/install.sh" connect --runtime host
run_case 'sandbox removal requires consent' expect_failure 'pass --yes' bash "$SCRIPT_DIR/uninstall.sh" --runtime openshell --harness openclaw
run_case 'scoped sandbox removal requires OpenShell runtime' expect_failure 'requires --runtime openshell' bash "$SCRIPT_DIR/uninstall.sh" --runtime host --sandbox-only --yes
run_case 'live suite requires explicit opt-in' expect_failure 'Set HARNESS_RUN_OPENSHELL_INTEGRATION=1' \
  env -u HARNESS_RUN_OPENSHELL_INTEGRATION bash "$SCRIPT_DIR/test/openshell-integration-test.sh"
run_case 'managed Qwen inference regression suite' bash "$SCRIPT_DIR/test/managed-inference-test.sh"
run_case 'model switch and complete uninstall regression suite' bash "$SCRIPT_DIR/test/model-lifecycle-test.sh"
run_case 'Qwen local-model defaults regression suite' node --test "$SCRIPT_DIR/test/model-defaults-test.mjs"
run_case 'Hermes policy adds only sandbox-local PTY paths to the base policy' node -e '
  const fs=require("node:fs"),assert=require("node:assert/strict"),root=process.argv[1];
  const normalize=s=>s.split("\n").filter(x=>x.trim()&&!x.trim().startsWith("#")).join("\n");
  const base=fs.readFileSync(`${root}/openshell/policy.yaml`,"utf8");
  const hermes=fs.readFileSync(`${root}/openshell/hermes-policy.yaml`,"utf8");
  for(const p of ["/dev/ptmx","/dev/pts"]) assert.equal(hermes.split(`    - ${p}\n`).length,2);
  assert.equal(normalize(hermes.replace("    - /dev/ptmx\n","").replace("    - /dev/pts\n","")),normalize(base));
  assert.ok(fs.readFileSync(`${root}/scripts/lib/openshell.sh`,"utf8").includes(
    "[[ \"$agent\" != hermes ]] || policy=\"${SCRIPT_DIR}/openshell/hermes-policy.yaml\""));
' "$SCRIPT_DIR"
finish_tests
