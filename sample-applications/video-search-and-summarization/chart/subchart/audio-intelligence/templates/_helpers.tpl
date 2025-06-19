{{/*
Expand the name of the chart.
*/}}
{{- define "audiointelligence.name" -}}
{{- default .Chart.Name .Values.audiointelligence.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "audiointelligence.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "audiointelligence.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}


