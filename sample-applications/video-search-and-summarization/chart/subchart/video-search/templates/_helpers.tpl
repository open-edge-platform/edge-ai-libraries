{{/*
Expand the name of the chart.
*/}}
{{- define "videosearch.name" -}}
{{- default .Chart.Name .Values.videosearch.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "videosearch.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "videosearch.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}


