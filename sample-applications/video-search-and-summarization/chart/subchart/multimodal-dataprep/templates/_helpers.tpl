{{/*
Expand the name of the chart.
*/}}
{{- define "vdms-dataprep.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "vdms-dataprep.fullname" -}}
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
{{- define "vdms-dataprep.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "vdms-dataprep.labels" -}}
helm.sh/chart: {{ include "vdms-dataprep.chart" . }}
{{ include "vdms-dataprep.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "vdms-dataprep.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vdms-dataprep.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/app: {{ include "vdms-dataprep.fullname" . }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "vdms-dataprep.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "vdms-dataprep.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
