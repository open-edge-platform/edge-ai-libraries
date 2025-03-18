{{/*
Expand the name of the chart.
*/}}
{{- define "chatqna-core.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default chart name.
*/}}
{{- define "chatqna-core.chartName" -}}
{{- .Chart.Name -}}
{{- end -}}

{{/*
Create a default release name.
*/}}
{{- define "chatqna-core.releaseName" -}}
{{- .Release.Name -}}
{{- end -}}

{{/*
Define the name for nginx Chart.
*/}}
{{- define "nginx.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-nginx
{{- end }}
