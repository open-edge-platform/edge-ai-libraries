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

{{- define "vlminference.validateDeploymentOptions" -}}
{{- $ovmsgpu := .Values.global.gpu.ovmsEnabled | default false }}
{{- $vlmgpu := .Values.global.gpu.vlminferenceEnabled | default false }}
{{- if and $ovmsgpu $vlmgpu }}
{{- fail "vlmInference cannot run with GPU if OVMS is running with GPU. Please set vlminferenceEnabled to false." }}
{{- end }}
{{- end }}