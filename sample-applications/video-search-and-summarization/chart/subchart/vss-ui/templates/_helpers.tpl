{{/*
Expand the name of the chart.
*/}}
{{- define "vssui.name" -}}
  {{- default .Chart.Name (default "" .Values.name) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a fully qualified app name.
*/}}
{{- define "vssui.fullname" -}}
  {{- $name := default .Chart.Name (default "" .Values.name) -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
