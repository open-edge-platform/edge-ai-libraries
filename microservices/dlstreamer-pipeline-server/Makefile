#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

all:
	@# Help: Runs build, lint, test stages
	build lint test

build:
	@# Help: Runs build stage
	@echo "---MAKEFILE BUILD---"
	# docker compose build
	@sh tests/build.sh
	@echo "---END MAKEFILE Build---"

lint:
	@# Help: Runs lint stage
	@echo "---MAKEFILE LINT---"
	echo $@
	@echo "---END MAKEFILE LINT---"

test:
	@# Help: Runs test stage
	@echo "---MAKEFILE TEST---"

	docker run --entrypoint /home/pipeline-server/tests/run_tests.sh -v /tmp:/tmp:rw intel/dlstreamer-pipeline-server-test:3.1.0
	@echo "---END MAKEFILE TEST---"

coverage:
	@# Help: Runs coverage stage
	@echo "---MAKEFILE COVERAGE---"
	echo $@
	@echo "---END MAKEFILE COVERAGE---"

list:
	@# Help: displays make targets
	help

help:
	@printf "%-20s %s\n" "Target" "Description"
	@printf "%-20s %s\n" "------" "-----------"
	@make -pqR : 2>/dev/null \
        | awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}' \
        | sort \
        | egrep -v -e '^[^[:alnum:]]' -e '^$@$$' \
        | xargs -I _ sh -c 'printf "%-20s " _; make _ -nB | (grep -i "^# Help:" || echo "") | tail -1 | sed "s/^# Help: //g"'


.PHONY: build test coverage
