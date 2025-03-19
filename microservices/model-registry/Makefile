#****************************************************************************
#
# Copyright (C) 2022 Intel Corporation
# 
# THIS SOFTWARE AND THE RELATED DOCUMENTS ARE INTEL COPYRIGHTED MATERIALS,
# AND YOUR USE OF THEM IS GOVERNED BY THE EXPRESS LICENSE UNDER WHICH THEY
# WERE PROVIDED TO YOU ("LICENSE"). UNLESS THE LICENSE PROVIDES OTHERWISE, 
# YOU MAY NOT USE, MODIFY, COPY, PUBLISH, DISTRIBUTE, DISCLOSE OR TRANSMIT
# THIS SOFTWARE OR THE RELATED DOCUMENTS WITHOUT INTEL'S PRIOR 
# WRITTEN PERMISSION.
#
# This software and the related documents are provided as is, with no express 
# or implied warranties, other than those that are expressly stated in 
# the License.
#
#****************************************************************************

all: 
	@# Help: Runs build, lint, test stages
	build lint test 	
	
build:
	@# Help: Runs build stage
	@echo "---MAKEFILE BUILD---"
	echo $@
	@echo "---END MAKEFILE Build---"

lint:
	@# Help: Runs lint stage
	@echo "---MAKEFILE LINT---"
	echo $@
	@echo "---END MAKEFILE LINT---"
	
install-dependencies:
	@# Help: Runs install-dependencies stage
	@echo "---MAKEFILE INSTALL DEPENDENCIES---"
	pip3 install -r requirements.txt \
		 -r tests/requirements-tests.txt
	@echo "---END MAKEFILE INSTALL DEPENDENCIES---"

test:
	@# Help: Runs test stage
	@echo "---MAKEFILE TEST---"
	pytest -vv --cov=src --cov-report term-missing
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
	
