# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

.PHONY: tests-image tests-run image dirs decoder encoder run rm dlstreamer-up dlstreamer-down certs certs-trust certs-clean fuzz-services pull-model

.DEFAULT_GOAL := image

RESTLER_BIN ?= restler
FUZZ_MINUTES ?= 30
FUZZ_RESULTS_DIR := evidence/restler

MODEL_DIR := models/obj_det_models
YOLO_MODEL_NAME ?= yolov8m
YOLO_MODEL_URL := https://huggingface.co/Ultralytics/YOLOv8/resolve/main/$(YOLO_MODEL_NAME).pt
YOLO_MODEL_OUT_DIR := $(MODEL_DIR)/$(YOLO_MODEL_NAME)_int8_openvino_model

DEFAULT_CONFIG := configs/default.yaml
CONTAINER_DEFAULT_CONFIG := /app/$(DEFAULT_CONFIG)

detector_backend = $$(docker run --rm --entrypoint sh image-pipeline -c "grep -m1 '^[[:space:]]*detector_backend:' $(CONTAINER_DEFAULT_CONFIG) | sed 's/\#.*//' | cut -d: -f2 | tr -d '[:space:]'")

HAS_NPU := $(shell test -e /dev/accel/accel0 && echo 1)
NPU_RENDER_GID = $$(stat -c '%g' /dev/accel/accel0)

tests-image: ## Build the Docker images for tests
	cp .dockerignore.test .dockerignore
	docker build -t image-pipeline-tests -f Dockerfile.test .
	git restore .dockerignore

tests-run: ## Run the tests inside the container
	docker run --rm image-pipeline-tests

image: ## Build the main Docker image that is intented for end-user
	docker build -t image-pipeline -f Dockerfile .

dirs: ## Create necessary directories and change ownership
	mkdir -p output data log
	sudo chown -R 1999:1999 output data log

decoder: ## Run decoder
	docker compose up -d decoder

encoder: ## Run encoder with NPU (if present) and fall back to CPU otherwise
	if [ "$(detector_backend)" = "dlstreamer" ] && [ "$(HAS_NPU)" = "1" ]; then \
		NPU_RENDER_GID="$(NPU_RENDER_GID)" docker compose --profile npu up -d --wait dlstreamer-pipeline-server-gpu-npu; \
	elif [ "$(detector_backend)" = "dlstreamer" ]; then \
		docker compose up -d --wait dlstreamer-pipeline-server; \
	fi
ifeq ($(HAS_NPU),1)
	NPU_RENDER_GID="$(NPU_RENDER_GID)" docker compose --profile npu up -d encoder-npu
else
	docker compose up -d encoder
endif

clean: ## Tear down the running containers and remove orphans
	NPU_RENDER_GID=0 docker compose --profile npu down --remove-orphans

pull-model: dirs ## Downloads yolov8m and change it to OpenVINO format.
	pip install -r requirements.txt
	mkdir -p "$(MODEL_DIR)"
	curl -fL "$(YOLO_MODEL_URL)" -o "$(MODEL_DIR)/$(YOLO_MODEL_NAME).pt"
	rm -rf "$(YOLO_MODEL_OUT_DIR)"
	rm -rf "src/datasets/coco8"
	python3 -c "from ultralytics import YOLO; YOLO('$(MODEL_DIR)/$(YOLO_MODEL_NAME).pt').export(format='openvino', int8=True)"
	mv "$(YOLO_MODEL_OUT_DIR)/$(YOLO_MODEL_NAME).xml" "$(YOLO_MODEL_OUT_DIR)/best.xml"
	mv "$(YOLO_MODEL_OUT_DIR)/$(YOLO_MODEL_NAME).bin" "$(YOLO_MODEL_OUT_DIR)/best.bin"
	rm "$(MODEL_DIR)/$(YOLO_MODEL_NAME).pt"

fuzz-services: image dirs ## Fuzz the encoder/decoder REST services using RESTler
	if [ "$(detector_backend)" = "dlstreamer" ]; then $(MAKE) dlstreamer-up; fi
	$(MAKE) decoder encoder
	mkdir -p $(FUZZ_RESULTS_DIR)
	repo_root="$$(pwd)"; \
	per_service_min=$$(( $(FUZZ_MINUTES) / 2 )); \
	time_budget_hours=$$(awk -v m="$$per_service_min" 'BEGIN { printf "%.4f", m / 60 }'); \
	for svc_port in "encoder:8001" "decoder:8002"; do \
		svc="$${svc_port%%:*}"; port="$${svc_port##*:}"; \
		spec="$$repo_root/$(FUZZ_RESULTS_DIR)/$${svc}-openapi.json"; \
		compiled="$$repo_root/$(FUZZ_RESULTS_DIR)/$${svc}-compile"; \
		results="$$repo_root/$(FUZZ_RESULTS_DIR)/$${svc}-fuzz"; \
		echo "==> Fetching OpenAPI spec for $$svc from http://localhost:$$port/openapi.json"; \
		curl -fsS "http://localhost:$$port/openapi.json" -o "$$spec" || exit 1; \
		rm -rf "$$compiled" "$$results"; mkdir -p "$$compiled" "$$results"; \
		echo "==> Compiling RESTler grammar for $$svc"; \
		$(RESTLER_BIN) --workingDirPath "$$compiled" compile --api_spec "$$spec" || exit 1; \
		echo "==> Fuzzing $$svc on port $$port for $$per_service_min min (time_budget=$${time_budget_hours}h)"; \
		$(RESTLER_BIN) --workingDirPath "$$results" fuzz \
			--grammar_file "$$compiled/Compile/grammar.py" \
			--dictionary_file "$$compiled/Compile/dict.json" \
			--settings "$$compiled/Compile/engine_settings.json" \
			--target_ip localhost \
			--target_port $$port \
			--time_budget $$time_budget_hours \
			--no_ssl \
			--no_results_analyzer || exit 1; \
	done

help: ## Show this help
	@awk ' \
		/^# [A-Za-z]/ { \
			gsub(/^# /,""); printf "\n\033[1m%s\033[0m\n", $$0; next \
		} \
		/^[a-zA-Z_-]+:.*?## / { \
			split($$0, a, ":.*?## "); printf "  %-22s %s\n", a[1], a[2] \
		} \
	' $(MAKEFILE_LIST)