{{/*
Expand the name of the chart.
*/}}
{{- define "audioanalyzer.name" -}}
{{- default .Chart.Name .Values.audioanalyzer.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "audioanalyzer.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "audioanalyzer.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}


