{{/*
Expand the name of the chart.
*/}}
{{- define "minioServer.name" -}}
{{- default .Chart.Name .Values.minioServer.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "minioServer.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "minioServer.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}


