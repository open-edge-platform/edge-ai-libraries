{{/*
Expand the name of the chart.
*/}}
{{- define "chatqna-core.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default chart name.
*/}}
{{- define "chatqna-core.chartName" -}}
{{- .Chart.Name -}}
{{- end -}}

{{/*
Create a default release name.
*/}}
{{- define "chatqna-core.releaseName" -}}
{{- .Release.Name -}}
{{- end -}}

{{/*
Define the name for nginx Chart.
*/}}
{{- define "nginx.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-nginx
{{- end }}

{{- define "chatqna-core.validateGpuSettings" -}}
{{- $backend := .Values.global.MODEL_RUNTIME | lower }}
{{- if eq $backend "ollama" }}
  {{- if or (eq .Values.global.EMBEDDING_DEVICE "GPU") (eq .Values.global.LLM_DEVICE "GPU") }}
    {{- fail "MODEL_RUNTIME is set to 'ollama', but EMBEDDING_DEVICE or LLM_DEVICE is set to 'GPU'. Ollama backend only supports CPU devices." }}
  {{- end }}

{{- if and (not .Values.gpu.enabled) (or (eq .Values.global.EMBEDDING_DEVICE "GPU") (eq .Values.global.RERANKER_DEVICE "GPU") (eq .Values.global.LLM_DEVICE "GPU")) }}
{{- fail "GPU is disabled, but one or more model devices are set to 'GPU'. Please set EMBEDDING_DEVICE, RERANKER_DEVICE, and LLM_DEVICE to 'CPU' or enable GPU." }}
{{- end }}

{{- end }}
{{- end }}