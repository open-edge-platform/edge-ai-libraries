
{{/*
Expand the name of the chart.
*/}}
{{- define "chatqna-helm-chart.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Expand the full name of the chart.
*/}}
{{- define "chatqna-helm-chart.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" $name .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Create a default chart label.
*/}}
{{- define "chatqna-helm-chart.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "chatqna-helm-chart.labels" -}}
helm.sh/chart: {{ include "chatqna-helm-chart.chart" . }}
{{ include "chatqna-helm-chart.selectorLabels" . }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "chatqna-helm-chart.selectorLabels" -}}
app.kubernetes.io/name: {{ include "chatqna-helm-chart.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Define the name for nginx Chart.
*/}}
{{- define "nginx.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-nginx
{{- end }}

{{/*
Define the name for chatqnaui Chart.
*/}}
{{- define "chatqnaui.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-
{{- end }}

{{/*
Define the name for chatqna Chart.
*/}}
{{- define "chatqna.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-
{{- end }}

{{/*
Define the name for dataprepPgvector Chart.
*/}}
{{- define "dataprepPgvector.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-
{{- end }}


{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "Chatqna.fullname" -}}
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