{{/*
Expand the name of the chart.
*/}}
{{- define "videoingestion.name" -}}
  {{- default .Chart.Name (default "" .Values.videoingestion.name) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a fully qualified app name.
*/}}
{{- define "videoingestion.fullname" -}}
  {{- $name := default .Chart.Name .Values.videoingestion.fullname -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
