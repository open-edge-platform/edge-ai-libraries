
{{/*
Expand the name of the chart.
*/}}
{{- define "video-summarization.name" -}}
{{- default "video-summarization" .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Expand the full name of the chart.
*/}}
{{- define "video-summarization.fullname" -}}
{{- $name := default "video-summarization" .Chart.Name -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default chart label.
*/}}
{{- define "video-summarization.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | default "video-summarization-1.0.0" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "video-summarization.labels" -}}
helm.sh/chart: {{ include "video-summarization.chart" . }}
{{ include "video-summarization.selectorLabels" . }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "video-summarization.selectorLabels" -}}
app.kubernetes.io/name: {{ include "video-summarization.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Define the name for nginx Chart.
*/}}
{{- define "nginx.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-nginx
{{- end }}

{{/*
Define the name for pipelineManager Chart.
*/}}
{{- define "pipelinemanager.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-{{ .Values.pipelinemanager.name }}
{{- end }}

{{/*
Define the name for minioServer Chart.
*/}}
{{- define "minioServer.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-{{ .Values.minioServer.name }}
{{- end }}

{{/*
Define the name for audioanalyzer Chart.
*/}}
{{- define "audioanalyzer.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-{{ .Values.audioanalyzer.name }}
{{- end }}

{{/*
Define the name for videoingestion Chart.
*/}}
{{- define "videoingestion.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-{{ .Values.videoingestion.name }}
{{- end }}

{{/*
Define the name for vss-collector.
*/}}
{{- define "vsscollector.fullname" -}}
{{ .Release.Name | trunc 57 | trimSuffix "-" }}-{{ .Values.vsscollector.name }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "video-summarization.qualified-fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride | default "video-summarization" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
No-op placeholder for chart-level validations.
*/}}
{{- define "video-summarization.validateGpuPairing" -}}
{{- end -}}

{{/*
Compose an image reference with an optional single-source global registry/tag override.

Args (dict):
  registry   - global.registry; when set, the image is pulled from this registry and only the
               bare image name (base of repository) is kept (e.g. "intel/pipeline-manager" -> "pipeline-manager").
  repository - the chart's default repository (may include a registry/namespace prefix).
  tag        - the already-resolved tag to use.

When registry is empty the repository is used verbatim, preserving existing behavior.
*/}}
{{- define "vss.image" -}}
{{- $registry := .registry | default "" -}}
{{- $repository := .repository -}}
{{- $tag := .tag -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" (trimSuffix "/" $registry) (base $repository) $tag -}}
{{- else -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end -}}
