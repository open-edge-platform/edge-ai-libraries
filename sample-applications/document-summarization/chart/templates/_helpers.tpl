{{/*
Define the name for nginx Chart.
*/}}
{{- define "nginx.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-nginx
{{- end }}