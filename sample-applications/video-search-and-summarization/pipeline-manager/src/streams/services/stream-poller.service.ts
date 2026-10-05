// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { SocketEvent } from 'src/events/socket.events';
import { StreamShimService } from './stream-shim.service';

/**
 * Polls dataprep for live-stream state and emits a socket sync on change.
 *
 * dataprep offers no webhook, so a poll is the only option. The cost of
 * getting the guard wrong is a permanent background request loop in every
 * deployment, so it is gated twice:
 *
 *  1. `streams.endpoint` must be configured. In summary-only mode
 *     `SEARCH_DATAPREP_ENDPOINT` is empty and dataprep is not deployed at
 *     all; polling there would fail every tick forever.
 *  2. At least one client must have joined the `streams` room. The UI joins
 *     when the Live Streams modal opens and leaves when it closes, so an idle
 *     deployment polls zero times. Gating on "a socket is connected" would be
 *     equivalent to always-on, because the UI opens its socket at app load.
 */
@Injectable()
export class StreamPollerService implements OnModuleDestroy {
  /** Room name shared with EventsGateway. */
  static readonly ROOM = 'streams';

  private readonly logger = new Logger(StreamPollerService.name);
  private timer: NodeJS.Timeout | null = null;
  private subscribers = 0;
  private lastError: string | null = null;
  private inFlight = false;

  constructor(
    private readonly $config: ConfigService,
    private readonly $shim: StreamShimService,
    private readonly $emitter: EventEmitter2,
  ) {}

  private get intervalMs(): number {
    return this.$config.get<number>('streams.pollIntervalMs') ?? 5000;
  }

  get subscriberCount(): number {
    return this.subscribers;
  }

  get isPolling(): boolean {
    return this.timer !== null;
  }

  /** Called by the gateway when a client joins the streams room. */
  addSubscriber(): void {
    this.subscribers += 1;
    this.start();
  }

  /** Called by the gateway on unsubscribe or disconnect. */
  removeSubscriber(): void {
    this.subscribers = Math.max(0, this.subscribers - 1);
    if (this.subscribers === 0) {
      this.stop();
    }
  }

  private start(): void {
    if (this.timer) return;

    if (!this.$shim.isConfigured) {
      // Logged once per activation, not once per tick.
      this.logger.warn(
        'Live stream polling skipped: no dataprep endpoint configured',
      );
      return;
    }

    this.logger.log(`Starting live stream poll every ${this.intervalMs}ms`);
    // Push a snapshot straight away so a newly opened modal is not blank for
    // up to a full interval.
    void this.poll();
    this.timer = setInterval(() => void this.poll(), this.intervalMs);
  }

  private stop(): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null;
    this.lastError = null;
    this.logger.log('Stopped live stream poll (no subscribers)');
  }

  /**
   * Fetch and emit.
   *
   * Emits on **every** tick rather than only on change. Diffing was the
   * original design, but the fields a watcher cares most about —
   * `frames_processed`, `uptime_seconds`, `last_frame_ts` — advance on every
   * tick by nature. Any fingerprint that excludes them freezes the counters in
   * the UI; any fingerprint that includes them marks every poll as a change,
   * so the diff saves nothing. Since the room is non-empty only while someone
   * has the modal open, an unconditional emit every `intervalMs` is both
   * correct and bounded.
   *
   * `inFlight` prevents overlapping requests if dataprep is slower than the
   * poll interval.
   */
  async poll(): Promise<void> {
    if (this.inFlight) return;
    this.inFlight = true;
    try {
      const { streams } = await this.$shim.list();
      this.lastError = null;
      this.$emitter.emit(SocketEvent.STREAMS_SYNC, streams ?? []);
    } catch (error) {
      // A camera dropping out is routine and dataprep may restart under us;
      // log the first occurrence of each distinct failure, then stay quiet so
      // a persistent outage does not fill the log at one line every 5 s.
      const message =
        error instanceof Error ? error.message : 'unknown error';
      if (message !== this.lastError) {
        this.lastError = message;
        this.logger.warn(`Live stream poll failed: ${message}`);
      }
    } finally {
      this.inFlight = false;
    }
  }

  onModuleDestroy(): void {
    this.stop();
  }
}
