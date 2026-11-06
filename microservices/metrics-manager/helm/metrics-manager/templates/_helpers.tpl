{{/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation */}}
{{/* SPDX-License-Identifier: Apache-2.0 */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "metrics-manager.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully qualified app name. Truncated to 63 chars to satisfy the
DNS label limit (RFC 1123).
*/}}
{{- define "metrics-manager.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "metrics-manager.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "metrics-manager.labels" -}}
helm.sh/chart: {{ include "metrics-manager.chart" . }}
{{ include "metrics-manager.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: edge-ai-libraries
{{- end }}

{{- define "metrics-manager.selectorLabels" -}}
app.kubernetes.io/name: {{ include "metrics-manager.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "metrics-manager.serviceAccountName" -}}
{{- if .Values.pod.serviceAccount.create }}
{{- default (include "metrics-manager.fullname" .) .Values.pod.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.pod.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference. Falls back to .Chart.AppVersion when image.tag is empty.
*/}}
{{- define "metrics-manager.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end }}

{{- define "metrics-manager.collectorOptions" -}}
enableRapl: ENABLE_RAPL
enablePowerstatExtra: ENABLE_POWERSTAT_EXTRA
enableTurbostat: ENABLE_TURBOSTAT
enableTemperature: ENABLE_TEMPERATURE
enableInterrupts: ENABLE_INTERRUPTS
enableNetwork: ENABLE_NETWORK
enableNetworkVirtual: ENABLE_NETWORK_VIRTUAL
enableStorage: ENABLE_STORAGE
{{- end }}

{{- define "metrics-manager.validate" -}}
{{/* Reused legacy values can omit nested defaults introduced by this chart. */}}
{{- range $key := list "enableRaplPower" "enableDramBw" "enableDiskIo" "enableNetIo" "enableTempStats" "enablePsysPower" "enableGpuThrottle" "hardwareTelemetryEnabled" -}}
  {{- if hasKey $.Values.config $key -}}
    {{- fail (printf "config.%s was removed in 2026.3.0; migrate your values using the Helm deployment guide (do not use --reuse-values)" $key) -}}
  {{- end -}}
{{- end -}}
{{- $booleans := dict "hardware.telemetry.enabled" .Values.hardware.telemetry.enabled "hardware.gpu.enabled" .Values.hardware.gpu.enabled "hardware.npu.enabled" .Values.hardware.npu.enabled "hardware.msr.enabled" .Values.hardware.msr.enabled "pod.hostPID" .Values.pod.hostPID "pod.hostNetwork" .Values.pod.hostNetwork "customMetrics.enabled" .Values.customMetrics.enabled "serviceMonitor.enabled" .Values.serviceMonitor.enabled "securityContext.privileged" .Values.securityContext.privileged "securityContext.allowPrivilegeEscalation" .Values.securityContext.allowPrivilegeEscalation "securityContext.runAsNonRoot" .Values.securityContext.runAsNonRoot "securityContext.readOnlyRootFilesystem" .Values.securityContext.readOnlyRootFilesystem "securityContext.appArmorProfileForce" .Values.securityContext.appArmorProfileForce -}}
{{- range $key, $value := $booleans -}}
  {{- if not (kindIs "bool" $value) -}}
    {{- fail (printf "%s must be a YAML boolean, not a string" $key) -}}
  {{- end -}}
{{- end -}}
{{- if not (has .Values.controller.kind (list "Deployment" "DaemonSet")) -}}
  {{- fail "controller.kind must be Deployment or DaemonSet" -}}
{{- end -}}
{{- if not (has .Values.customMetrics.storage (list "emptyDir" "pvc" "none")) -}}
  {{- fail "customMetrics.storage must be emptyDir, pvc or none" -}}
{{- end -}}
{{- $ports := list -}}
{{- range $key := list "metricsPort" "telegrafPort" "telegrafHttpPort" -}}
  {{- $port := index $.Values.service $key | toString -}}
  {{- if or (not (regexMatch "^[1-9][0-9]{0,4}$" $port)) (gt (int $port) 65535) (has $port $ports) -}}
    {{- fail "service ports must be distinct integers between 1 and 65535" -}}
  {{- end -}}
  {{- $ports = append $ports $port -}}
{{- end -}}
{{- range $key, $env := include "metrics-manager.collectorOptions" . | fromYaml -}}
  {{- if not (has (index $.Values.config $key | toString) (list "true" "false")) -}}
    {{- fail (printf "config.%s must be true or false" $key) -}}
  {{- end -}}
{{- end -}}
{{- if not (regexMatch "^[1-9][0-9]{0,9}$" (.Values.config.turbostatInterval | toString)) -}}
  {{- fail "config.turbostatInterval must be positive integer seconds" -}}
{{- end -}}
{{- if gt (int64 .Values.config.turbostatInterval) 9223372036 -}}
  {{- fail "config.turbostatInterval exceeds the supported duration" -}}
{{- end -}}
{{- if eq (.Values.config.enableTurbostat | toString) "true" -}}
  {{- if not (and .Values.hardware.telemetry.enabled .Values.hardware.msr.enabled .Values.hardware.turbostat.hostPath) -}}
    {{- fail "Turbostat requires hardware.telemetry.enabled, hardware.msr.enabled and hardware.turbostat.hostPath" -}}
  {{- end -}}
{{- end -}}
{{- if and .Values.hardware.turbostat.hostPath (not (regexMatch "^/[a-zA-Z0-9_./+-]+$" .Values.hardware.turbostat.hostPath)) -}}
  {{- fail "hardware.turbostat.hostPath must be an absolute executable path without spaces" -}}
{{- end -}}
{{- if and (not .Values.hardware.telemetry.enabled) (or .Values.hardware.npu.enabled .Values.hardware.msr.enabled .Values.hardware.turbostat.hostPath) -}}
  {{- fail "NPU/MSR/Turbostat host mounts require hardware.telemetry.enabled=true" -}}
{{- end -}}
{{- range $name, $config := .Values.telegraf.extraConfigs -}}
  {{- if or (not (regexMatch "^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*\\.conf$" $name)) (not (kindIs "string" $config)) -}}
    {{- fail "telegraf.extraConfigs must map simple *.conf filenames to strings" -}}
  {{- end -}}
{{- end -}}
{{- $reserved := list "METRICS_PORT" "TELEGRAF_PORT" "TELEGRAF_HTTP_PORT" "TELEGRAF_HTTP_ENDPOINT" "PROMETHEUS_TELEGRAF_ENDPOINT" "LOG_LEVEL" "LOG_FORMAT" "CORS_ORIGINS" "METRICS_RETENTION_SECONDS" "MAX_METRICS_BATCH_SIZE" "HARDWARE_TELEMETRY_ENABLED" "QMASSA_FIFO_PATH" "METRICS_MANAGER_HOSTNAME" "CUSTOM_METRICS_DIR" "TELEGRAF_CONFIG_PATH" "TURBOSTAT_BIN" "TURBOSTAT_INTERVAL" "QMASSA_LOG_TO_STDERR" "NPU_READER_LOG_FILE" "ENABLE_RAPL_POWER" "ENABLE_DRAM_BW" "ENABLE_DISK_IO" "ENABLE_NET_IO" "ENABLE_TEMP_STATS" "ENABLE_PSYS_POWER" "ENABLE_GPU_THROTTLE" -}}
{{- range $key, $env := include "metrics-manager.collectorOptions" . | fromYaml -}}
  {{- $reserved = append $reserved $env -}}
{{- end -}}
{{- range .Values.config.extraEnv -}}
  {{- if or (not (kindIs "string" .name)) (not (regexMatch "^[A-Za-z_][A-Za-z0-9_]*$" .name)) -}}
    {{- fail "config.extraEnv entries require a valid environment variable name" -}}
  {{- end -}}
  {{- if has .name $reserved -}}
    {{- fail (printf "config.extraEnv contains managed, legacy or duplicate variable %s; use the documented chart values" .name) -}}
  {{- end -}}
  {{- $reserved = append $reserved .name -}}
{{- end -}}
{{- end -}}
