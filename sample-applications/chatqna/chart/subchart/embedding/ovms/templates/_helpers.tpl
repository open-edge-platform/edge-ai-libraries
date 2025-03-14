{{- define "openvino-model-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "openvino-model-server.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "openvino-model-server.name" . }}-{{ .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end -}}
{{- end -}}

{{- define "openvino-model-server.labels" -}}
helm.sh/chart: {{ include "openvino-model-server.chart" . }}
{{ include "openvino-model-server.selectorLabels" . }}
{{- end -}}

{{- define "openvino-model-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openvino-model-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "openvino-model-server.chart" -}}
{{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}