# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

.DEFAULT_GOAL := help
.PHONY: all lint clean help

# Shell config variable
SHELL	    := bash -eu -o pipefail

# directories
CI_DIR    := ci
CACHE_DIR := .cache

#### Python venv Target ####
VENV_DIR  := venv_ci

$(VENV_DIR): requirements.txt
	python3 -m venv $@ ;\
  set +u; . ./$@/bin/activate; set -u ;\
  python -m pip install --upgrade pip ;\
  python -m pip install -r requirements.txt

lint: yamllint shellcheck markdownlint actionlint ## lint all files in repo

license: $(VENV_DIR) ## Check licensing with reuse
	set +u; . ./$</bin/activate; set -u ;\
  reuse --version ;\
  reuse --root . lint

YAML_FILES := $(shell find . -type f \( -name '*.yaml' -o -name '*.yml' \) -print )
yamllint: $(VENV_DIR) ## Lint YAML files with yamllint
	set +u; . ./$</bin/activate; set -u ;\
  yamllint --version ;\
  yamllint -d '{extends: default, rules: {line-length: {max: 120}}, ignore: [$(VENV_DIR),$(CI_DIR),$(CACHE_DIR)]}' -s $(YAML_FILES)

# https://github.com/koalaman/shellcheck
SH_FILES := $(shell find . -type f -name '*.sh' ! -path './trivy/*')
shellcheck: ## lint shell scripts with shellcheck
	shellcheck --version
	shellcheck -x -S style $(SH_FILES)

# https://github.com/DavidAnson/markdownlint-cli2
markdownlint: ## lint markdown files with markdownlint-cli2
	markdownlint-cli2 '**/*.md'

actionlint: ## lint github actions
	go install github.com/rhysd/actionlint/cmd/actionlint@latest
	actionlint -shellcheck=

clean: ## cleanup all temporary files
	rm -rf $(VENV_DIR)

#### Help Target ####
help: ## print help for each target
	@echo orch-ci make targets
	@echo "Target               Makefile:Line    Description"
	@echo "-------------------- ---------------- -----------------------------------------"
	@grep -H -n '^[[:alnum:]%_-]*:.* ##' $(MAKEFILE_LIST) \
    | sort -t ":" -k 3 \
    | awk 'BEGIN  {FS=":"}; {sub(".* ## ", "", $$4)}; {printf "%-20s %-16s %s\n", $$3, $$1 ":" $$2, $$4};'
