{{/*
Expand the name of the chart.
*/}}
{{- define "minioserver.name" -}}
{{- default .Chart.Name .Values.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "minioserver.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "minioserver.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}


