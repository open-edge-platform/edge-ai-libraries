{{/*
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
*/}}
{{- define "metrics-manager.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "metrics-manager.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "metrics-manager.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "metrics-manager.deploymentFullname" -}}
{{- if .Values.deploymentNameOverride }}
{{- .Values.deploymentNameOverride | trunc 63 | trimSuffix "-" }}
{{- else if .Values.fullnameOverride }}
{{- printf "%s-%s" .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "metrics-manager.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "metrics-manager.selectorLabels" -}}
app.kubernetes.io/name: {{ include "metrics-manager.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "metrics-manager.labels" -}}
{{ include "metrics-manager.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
