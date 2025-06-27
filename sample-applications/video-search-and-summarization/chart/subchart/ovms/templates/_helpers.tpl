{{/*
Expand the name of the chart.
*/}}
{{- define "ovms.name" -}}
{{- default .Chart.Name .Values.ovms.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ovms.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "ovms.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}


