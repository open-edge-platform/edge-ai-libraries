// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { SearchEvents } from 'src/events/Pipeline.events';
import { SocketEvent } from 'src/events/socket.events';
import { LiveStreamState } from '../models/stream.model';
import { StreamShimService } from './stream-shim.service';

/**
 * Polls dataprep for live-stream state, pushes a socket sync to the UI, and
 * marks the search index dirty when live ingestion produces new embeddings.
 *
 * dataprep offers no webhook, so a poll is the only option. The cost of
 * getting the guard wrong is a permanent background request loop in every
 * deployment, so polling only runs when BOTH:
 *
 *  1. `streams.endpoint` is configured. In summary-only mode
 *     `SEARCH_DATAPREP_ENDPOINT` is empty and dataprep is not deployed at
 *     all; polling there would fail every tick forever.
 *  2. There is something worth polling for — either a UI client has joined the
 *     `streams` room (Live Streams view open) OR at least one registered
 *     stream is still `running`.
 *
 * The second condition is what keeps watched-query auto-refresh working during
 * live ingestion even when nobody has the Live Streams view open: the poll is
 * the only source of the live EMBEDDINGS_UPDATE signal, so it must stay alive
 * while a stream runs, not just while the stream UI is visible. An idle
 * deployment (no subscribers, no running streams) stops polling after the
 * first tick that observes nothing active.
 */
@Injectable()
export class StreamPollerService implements OnModuleInit, OnModuleDestroy {
  /** Room name shared with EventsGateway. */
  static readonly ROOM = 'streams';

  private readonly logger = new Logger(StreamPollerService.name);
  private timer: NodeJS.Timeout | null = null;
  private subscribers = 0;
  /**
   * Number of registered streams still `running` as of the last poll. Together
   * with `subscribers` this decides whether the poll loop stays alive: a
   * running stream keeps producing embeddings, so the loop must continue even
   * with the Live Streams view closed so watched queries keep refreshing.
   */
  private activeStreams = 0;
  private lastError: string | null = null;
  private inFlight = false;
  /**
   * Running total of embeddings across all live streams at the previous poll.
   * Live ingestion is continuous and never hits dataprep's per-request
   * EMBEDDINGS_UPDATE path, so watched ("checkmarked") queries would never
   * refresh while a stream runs. When this total grows between polls, new live
   * embeddings landed, so we emit EMBEDDINGS_UPDATE to mark the search index
   * dirty; the bounded-rate watch-refresh scheduler then coalesces these into
   * watched-query refreshes (parity with the single-video and batch flows).
   * `null` means "no baseline yet" so the first poll never fires a spurious
   * refresh.
   */
  private lastEmbeddingsTotal: number | null = null;

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
    this.ensurePolling();
  }

  /** Called by the gateway on unsubscribe or disconnect. */
  removeSubscriber(): void {
    this.subscribers = Math.max(0, this.subscribers - 1);
    this.maybeStop();
  }

  /**
   * Start the poll loop if it is not already running. Safe to call from any
   * activation source (a UI subscriber joining, a stream being registered, or
   * startup recovery) — the loop self-terminates on the first idle poll.
   */
  ensurePolling(): void {
    this.start();
  }

  /** Stop polling once there is nothing left to poll for. */
  private maybeStop(): void {
    if (this.subscribers === 0 && this.activeStreams === 0) {
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
    this.lastEmbeddingsTotal = null;
    this.logger.log(
      'Stopped live stream poll (no subscribers or running streams)',
    );
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

      // Keep the loop alive while any stream is still running, independent of
      // UI subscribers, so live embeddings continue to drive watched-query
      // refreshes with the Live Streams view closed.
      this.activeStreams = (streams ?? []).filter(
        (stream) => stream?.state === LiveStreamState.RUNNING,
      ).length;

      // Trigger watched-query refresh when live ingestion produced new
      // embeddings since the last poll. dataprep has no webhook, so this poll
      // is the only signal that continuous live embeddings have landed.
      const embeddingsTotal = (streams ?? []).reduce(
        (sum, stream) => sum + (stream?.stats?.embeddings_created ?? 0),
        0,
      );
      if (
        this.lastEmbeddingsTotal !== null &&
        embeddingsTotal > this.lastEmbeddingsTotal
      ) {
        this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
      }
      this.lastEmbeddingsTotal = embeddingsTotal;
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
      // Self-terminate once nothing is left to poll for (no UI subscribers and
      // no running streams). A registration or a reopened view restarts it.
      this.maybeStop();
    }
  }

  /**
   * Resume polling on startup if dataprep already has running streams (e.g.
   * pipeline-manager restarted while a live stream kept ingesting). The first
   * poll stops the loop again if nothing is actually running.
   */
  onModuleInit(): void {
    this.ensurePolling();
  }

  onModuleDestroy(): void {
    this.stop();
  }
}
