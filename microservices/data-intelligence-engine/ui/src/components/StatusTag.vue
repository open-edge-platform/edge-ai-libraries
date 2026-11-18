<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-tag
    v-if="
      ['ready', 'reachable', 'reconciled', 'SERVING', 'exported'].includes(
        value,
      )
    "
    color="success"
    :bordered="false"
  >
    {{ !raw && $te(`console.${value}`) ? $t(`console.${value}`) : value }}
  </a-tag>
  <a-tag
    v-else-if="
      ['failed', 'extraction_failed', 'unreachable', 'unreconciled'].includes(
        value,
      )
    "
    color="error"
    :bordered="false"
  >
    {{ !raw && $te(`console.${value}`) ? $t(`console.${value}`) : value }}
  </a-tag>
  <a-tag
    v-else-if="
      [
        'pending',
        'indexing',
        'materializing',
        'PREPARING',
        'extracting',
        'extraction_pending',
        'extraction_waiting',
        'extraction_queued',
        'running',
        'queued',
      ].includes(value)
    "
    color="processing"
    :bordered="false"
  >
    {{ !raw && $te(`console.${value}`) ? $t(`console.${value}`) : value }}
  </a-tag>
  <a-tag v-else :bordered="false">
    {{ !raw && $te(`console.${value}`) ? $t(`console.${value}`) : value }}
  </a-tag>
</template>
<script lang="ts" setup name="StatusTag">
defineProps<{ value: string; raw?: boolean }>();
</script>
