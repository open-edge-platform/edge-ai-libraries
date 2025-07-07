{{/*
Expand the name of the chart.
*/}}
{{- define "vlminference.name" -}}
  {{- default .Chart.Name (default "" .Values.vlminference.name) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a fully qualified app name.
*/}}
{{- define "vlminference.fullname" -}}
  {{- $name := default .Chart.Name (default "" .Values.vlminference.name) -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
