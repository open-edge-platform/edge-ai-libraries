{{/*
Expand the name of the chart.
*/}}
{{- define "multimodal-dataprep.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "multimodal-dataprep.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "multimodal-dataprep.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "multimodal-dataprep.labels" -}}
helm.sh/chart: {{ include "multimodal-dataprep.chart" . }}
{{ include "multimodal-dataprep.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "multimodal-dataprep.selectorLabels" -}}
app.kubernetes.io/name: {{ include "multimodal-dataprep.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/app: {{ include "multimodal-dataprep.fullname" . }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "multimodal-dataprep.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "multimodal-dataprep.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
