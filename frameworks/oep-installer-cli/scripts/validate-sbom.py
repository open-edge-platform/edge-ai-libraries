#!/usr/bin/env python3
import sys, yaml
from jsonschema import Draft202012Validator

SCHEMA = {
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "openedge-cli list --sbom document (schema version 1)",
  "oneOf": [{ "$ref": "#/$defs/header" }, { "$ref": "#/$defs/component" }],
  "$defs": {
    "nonEmpty": { "type": "string", "minLength": 1 },
    "pkg": {
      "type": "string",
      "anyOf": [
        { "pattern": "^[a-z0-9][a-z0-9+.-]+(=[A-Za-z0-9.+~:-]+)?[*]?$" },
        { "pattern": "^[a-z0-9*?\\[][a-z0-9+.*?\\[\\]-]*$" },
        { "pattern": "^https://\\S+$" },
        { "pattern": "^http://\\S+$" },
        { "pattern": "^-[a-z0-9][a-z0-9+.-]+$" }
      ]
    },
    "header": {
      "type": "object",
      "required": ["schema-version", "cli-version", "module-list"],
      "properties": {
        "schema-version": { "const": "1" },
        "cli-version": { "$ref": "#/$defs/nonEmpty" },
        "module-list": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/nonEmpty" } }
      }
    },
    "url": {
      "type": "string",
      "anyOf": [
        { "pattern": "^https://\\S+$" },
        { "pattern": "^http://\\S+$" }
      ]
    },
    "component": {
      "type": "object",
      "not": { "required": ["schema-version"] },
      "properties": {
        "component": { "$ref": "#/$defs/nonEmpty" },
        "pkg-list": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/pkg" } },
        "kernel-cmdline": { "type": "array", "minItems": 1, "items": { "type": "string", "pattern": "^\\S+$" } },
        "apt-repository": { "enum": ["universe", "multiverse", "restricted"] },
        "repo-name": { "$ref": "#/$defs/nonEmpty" },
        "gpg-key": { "$ref": "#/$defs/url" },
        "gpg-key-fingerprint": { "type": "string", "pattern": "^[0-9A-F]{40}$" },
        "key-file": { "type": "string", "pattern": "^/[^\\s]+$" },
        "apt-source": { "type": "string", "pattern": "^deb (\\[[^\\]]*\\] )?https?://\\S+ \\S+ \\S+$" },
        "apt-src-source": { "type": "string", "pattern": "^deb-src " },
        "apt-list-file": { "type": "string", "pattern": "^/etc/apt/sources\\.list\\.d/[^/\\s]+$" },
        "apt-pref": { "type": "array", "minItems": 1, "items": { "type": "string" } },
        "apt-pref-file": { "type": "string", "pattern": "^/etc/apt/preferences\\.d/[^/\\s]+$" }
      },
      "dependentRequired": {
        "repo-name": ["gpg-key", "key-file", "apt-source", "apt-list-file"],
        "gpg-key": ["key-file", "apt-source", "apt-list-file"],
        "key-file": ["gpg-key", "apt-source", "apt-list-file"],
        "apt-source": ["gpg-key", "key-file", "apt-list-file"],
        "apt-list-file": ["gpg-key", "key-file", "apt-source"],
        "apt-src-source": ["apt-source"],
        "apt-pref": ["apt-pref-file"],
        "apt-pref-file": ["apt-pref"]
      },
      "anyOf": [
        { "required": ["pkg-list"] },
        { "required": ["kernel-cmdline"] },
        { "required": ["apt-source"] },
        { "required": ["apt-repository"] }
      ]
    }
  }
}

validator = Draft202012Validator(SCHEMA)
stream = open(sys.argv[2]) if len(sys.argv) > 2 else sys.stdin

failed = False
for i, doc in enumerate(yaml.safe_load_all(stream)):
    if doc is None:            # skip empty docs (e.g. trailing '---')
        continue
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    for e in errors:
        failed = True
        path = "/".join(map(str, e.path)) or "<root>"
        print(f"doc[{i}] {path}: {e.message}")
        for sub in sorted(e.context, key=lambda s: [str(p) for p in s.schema_path]):
            branch = sub.schema_path[0] if sub.schema_path else "?"
            subpath = "/".join(map(str, sub.path)) or "<root>"
            print(f"    oneOf[{branch}] {subpath}: {sub.message}")
    if not errors:
        print(f"doc[{i}] OK")
sys.exit(1 if failed else 0)

