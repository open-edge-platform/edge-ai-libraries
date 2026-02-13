// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import axios from 'axios';
import { mkdir, writeFile } from 'fs/promises';
import * as path from 'path';

const DEFAULT_INTERVAL_MS = 5000;
const DEFAULT_TIMEOUT_MS = 30000;
const SIGNAL_FILENAME = 'dataprep_embeddings_per_second.txt';

@Injectable()
export class DataprepTelemetryService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(DataprepTelemetryService.name);
  private poller?: NodeJS.Timeout;
  private lastErrorLogAt = 0;

  constructor(private readonly config: ConfigService) {}

  onModuleInit(): void {
    const interval = this.getIntervalMs();
    this.logger.log(`Starting dataprep telemetry poller (${interval}ms)`);
    this.poller = setInterval(() => {
      this.pollOnce().catch((err) => this.logError(err));
    }, interval);

    this.pollOnce().catch((err) => this.logError(err));
  }

  onModuleDestroy(): void {
    if (this.poller) {
      clearInterval(this.poller);
      this.poller = undefined;
    }
  }

  private getIntervalMs(): number {
    const raw = process.env.DATAPREP_TELEMETRY_INTERVAL_MS;
    const parsed = raw ? Number(raw) : DEFAULT_INTERVAL_MS;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_INTERVAL_MS;
  }

  private getTimeoutMs(): number {
    const raw = process.env.DATAPREP_TELEMETRY_TIMEOUT_MS;
    const parsed = raw ? Number(raw) : DEFAULT_TIMEOUT_MS;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_TIMEOUT_MS;
  }

  private resolveTelemetryUrl(): string | null {
    const explicit = process.env.DATAPREP_TELEMETRY_URL?.trim();
    if (explicit) return explicit;

    const base = this.config.get<string>('search.dataPrep');
    if (!base) return null;
    const trimmed = base.replace(/\/$/, '');
    if (trimmed.includes('/v1/dataprep')) {
      return `${trimmed.replace(/\/$/, '')}/telemetry?limit=1`;
    }
    return `${trimmed}/v1/dataprep/telemetry?limit=1`;
  }

  private resolveSignalPath(): string {
    const baseDir = process.env.TELEMETRY_SIGNAL_DIR || '/app/.collector-signals';
    return path.join(baseDir, SIGNAL_FILENAME);
  }

  private async pollOnce(): Promise<void> {
    try {
      const url = this.resolveTelemetryUrl();
      if (!url) {
        this.logError(new Error('Dataprep telemetry URL not configured'));
        return;
      }

      const response = await axios.get(url, { timeout: this.getTimeoutMs() });
      const value = response.data?.items?.[0]?.throughput?.embeddings_per_second;

      if (typeof value !== 'number' || Number.isNaN(value)) {
        return;
      }

      const targetPath = this.resolveSignalPath();
      await mkdir(path.dirname(targetPath), { recursive: true });
      await writeFile(targetPath, `${value}\n`, 'utf8');
    } catch (err) {
      this.logError(err);
    }
  }

  private logError(err: unknown): void {
    const now = Date.now();
    if (now - this.lastErrorLogAt < 30000) return;
    this.lastErrorLogAt = now;

    const message = err instanceof Error ? err.message : String(err);
    this.logger.warn(`Dataprep telemetry poll failed: ${message}`);
  }
}