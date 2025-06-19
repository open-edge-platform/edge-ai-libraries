{{/*
Expand the name of the chart.
*/}}
{{- define "rabbitmq.name" -}}
  {{- default .Chart.Name (default "" .Values.rabbitmq.name) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a fully qualified app name.
*/}}
{{- define "rabbitmq.fullname" -}}
  {{- $name := default .Chart.Name .Values.rabbitmq.fullname -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
