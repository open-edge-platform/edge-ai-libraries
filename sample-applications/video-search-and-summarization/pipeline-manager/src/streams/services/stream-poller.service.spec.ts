// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { Test, TestingModule } from '@nestjs/testing';
import { SocketEvent } from 'src/events/socket.events';
import { SearchEvents } from 'src/events/Pipeline.events';
import { LiveStreamState } from '../models/stream.model';
import { StreamShimService } from './stream-shim.service';
import { StreamPollerService } from './stream-poller.service';

describe('StreamPollerService', () => {
  let service: StreamPollerService;
  let list: jest.Mock;
  let emit: jest.Mock;
  let configured: boolean;

  const flush = async () => {
    // Let the floating promise inside the interval callback settle.
    await Promise.resolve();
    await Promise.resolve();
  };

  beforeEach(async () => {
    jest.useFakeTimers();
    configured = true;
    list = jest.fn().mockResolvedValue({ count: 0, streams: [] });
    emit = jest.fn();

    const shim = {
      list,
      get isConfigured() {
        return configured;
      },
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        StreamPollerService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) =>
              key === 'streams.pollIntervalMs' ? 5000 : undefined,
            ),
          },
        },
        { provide: StreamShimService, useValue: shim },
        { provide: EventEmitter2, useValue: { emit } },
      ],
    }).compile();

    service = module.get<StreamPollerService>(StreamPollerService);
  });

  afterEach(() => {
    service.onModuleDestroy();
    jest.useRealTimers();
  });

  describe('subscription lifecycle', () => {
    it('does not poll before anyone subscribes', async () => {
      jest.advanceTimersByTime(60000);
      await flush();
      expect(list).not.toHaveBeenCalled();
      expect(service.isPolling).toBe(false);
    });

    it('polls immediately on first subscribe so the modal is not blank', async () => {
      service.addSubscriber();
      await flush();
      expect(list).toHaveBeenCalledTimes(1);
      expect(service.isPolling).toBe(true);
    });

    it('polls on the configured interval', async () => {
      service.addSubscriber();
      await flush();
      list.mockClear();

      jest.advanceTimersByTime(5000);
      await flush();
      expect(list).toHaveBeenCalledTimes(1);

      jest.advanceTimersByTime(5000);
      await flush();
      expect(list).toHaveBeenCalledTimes(2);
    });

    it('starts only one interval for several subscribers', async () => {
      service.addSubscriber();
      service.addSubscriber();
      await flush();
      list.mockClear();

      jest.advanceTimersByTime(5000);
      await flush();
      expect(list).toHaveBeenCalledTimes(1);
    });

    it('keeps polling while any subscriber remains', async () => {
      service.addSubscriber();
      service.addSubscriber();
      service.removeSubscriber();
      expect(service.isPolling).toBe(true);
      expect(service.subscriberCount).toBe(1);
    });

    it('stops when the last subscriber leaves', async () => {
      service.addSubscriber();
      await flush();
      service.removeSubscriber();

      expect(service.isPolling).toBe(false);
      list.mockClear();
      jest.advanceTimersByTime(60000);
      await flush();
      expect(list).not.toHaveBeenCalled();
    });

    it('never drives the subscriber count below zero', () => {
      service.removeSubscriber();
      service.removeSubscriber();
      expect(service.subscriberCount).toBe(0);

      // A stray unsubscribe must not leave the counter negative, or the next
      // real subscriber would fail to start the loop.
      service.addSubscriber();
      expect(service.subscriberCount).toBe(1);
      expect(service.isPolling).toBe(true);
    });

    it('stops on module destroy', async () => {
      service.addSubscriber();
      await flush();
      service.onModuleDestroy();

      expect(service.isPolling).toBe(false);
      list.mockClear();
      jest.advanceTimersByTime(60000);
      await flush();
      expect(list).not.toHaveBeenCalled();
    });
  });

  describe('running-stream lifecycle (no subscribers)', () => {
    const runningStream = (embeddings = 0) => ({
      stream_id: 's1',
      state: LiveStreamState.RUNNING,
      stats: { embeddings_created: embeddings },
    });

    it('keeps polling while a stream runs even with no subscribers', async () => {
      list.mockResolvedValue({ count: 1, streams: [runningStream(10)] });
      service.ensurePolling();
      await flush();

      expect(service.isPolling).toBe(true);
      list.mockClear();
      jest.advanceTimersByTime(5000);
      await flush();
      expect(list).toHaveBeenCalledTimes(1);
    });

    it('stops once no stream is running and nobody is subscribed', async () => {
      list.mockResolvedValue({ count: 1, streams: [runningStream(10)] });
      service.ensurePolling();
      await flush();
      expect(service.isPolling).toBe(true);

      // The stream stops: the next poll observes nothing running and no
      // subscribers, so the loop self-terminates.
      list.mockResolvedValue({ count: 0, streams: [] });
      jest.advanceTimersByTime(5000);
      await flush();
      expect(service.isPolling).toBe(false);
    });

    it('marks the index dirty when live embeddings grow without a subscriber', async () => {
      list.mockResolvedValue({ count: 1, streams: [runningStream(10)] });
      service.ensurePolling();
      await flush();

      emit.mockClear();
      list.mockResolvedValue({ count: 1, streams: [runningStream(25)] });
      jest.advanceTimersByTime(5000);
      await flush();
      expect(emit).toHaveBeenCalledWith(SearchEvents.EMBEDDINGS_UPDATE);
    });

    it('resumes polling on startup when a stream is already running', async () => {
      list.mockResolvedValue({ count: 1, streams: [runningStream(10)] });
      service.onModuleInit();
      await flush();
      expect(service.isPolling).toBe(true);
    });

    it('self-terminates on startup when nothing is running', async () => {
      list.mockResolvedValue({ count: 0, streams: [] });
      service.onModuleInit();
      await flush();
      expect(service.isPolling).toBe(false);
    });

    it('keeps polling while a stream is non-terminal (reconnecting) with no subscribers', async () => {
      // A stream reconnecting/starting after a restart is not RUNNING yet, but
      // the loop must stay alive so the eventual running transition (which
      // happens on the dataprep side) still drives watched-query refresh.
      list.mockResolvedValue({
        count: 1,
        streams: [{ stream_id: 's1', state: LiveStreamState.RECONNECTING }],
      });
      service.onModuleInit();
      await flush();
      expect(service.isPolling).toBe(true);

      list.mockClear();
      jest.advanceTimersByTime(5000);
      await flush();
      expect(list).toHaveBeenCalledTimes(1);
    });

    it('keeps polling while a stream is paused so an out-of-band resume is caught', async () => {
      list.mockResolvedValue({
        count: 1,
        streams: [{ stream_id: 's1', state: LiveStreamState.PAUSED }],
      });
      service.onModuleInit();
      await flush();
      expect(service.isPolling).toBe(true);
    });

    it('self-terminates when every stream is terminal (stopped/error)', async () => {
      list.mockResolvedValue({
        count: 2,
        streams: [
          { stream_id: 's1', state: LiveStreamState.STOPPED },
          { stream_id: 's2', state: LiveStreamState.ERROR },
        ],
      });
      service.onModuleInit();
      await flush();
      expect(service.isPolling).toBe(false);
    });
  });

  describe('endpoint gate', () => {
    // In summary-only mode dataprep is not deployed and the endpoint is empty.
    // Polling there would fail every 5 s forever.
    it('refuses to start without a configured endpoint', async () => {
      configured = false;
      service.addSubscriber();
      await flush();

      expect(service.isPolling).toBe(false);
      expect(list).not.toHaveBeenCalled();
    });
  });

  describe('emission', () => {
    it('emits the stream list on every tick, including unchanged ones', async () => {
      // Counters such as frames_processed advance constantly; suppressing
      // unchanged emissions would freeze them in the UI.
      list.mockResolvedValue({
        count: 1,
        streams: [{ stream_id: 'a', state: 'running' }],
      });

      service.addSubscriber();
      await flush();
      expect(emit).toHaveBeenCalledWith(SocketEvent.STREAMS_SYNC, [
        { stream_id: 'a', state: 'running' },
      ]);

      emit.mockClear();
      jest.advanceTimersByTime(5000);
      await flush();
      expect(emit).toHaveBeenCalledTimes(1);
    });

    it('does not emit when the upstream call fails', async () => {
      list.mockRejectedValue(new Error('ECONNREFUSED'));
      service.addSubscriber();
      await flush();
      expect(emit).not.toHaveBeenCalled();
    });

    it('survives a failure and resumes on the next tick', async () => {
      list.mockRejectedValueOnce(new Error('transient'));
      service.addSubscriber();
      await flush();
      expect(emit).not.toHaveBeenCalled();

      list.mockResolvedValue({ count: 0, streams: [] });
      jest.advanceTimersByTime(5000);
      await flush();
      expect(emit).toHaveBeenCalledTimes(1);
    });

    it('does not overlap requests when upstream is slower than the interval', async () => {
      let release: (v: unknown) => void = () => undefined;
      list.mockReturnValue(new Promise((r) => (release = r)));

      service.addSubscriber();
      await flush();
      expect(list).toHaveBeenCalledTimes(1);

      jest.advanceTimersByTime(15000);
      await flush();
      expect(list).toHaveBeenCalledTimes(1);

      release({ count: 0, streams: [] });
      await flush();
    });
  });

  describe('watched-query refresh', () => {
    const streamWith = (embeddings: number) => ({
      count: 1,
      streams: [
        {
          stream_id: 'a',
          state: 'running',
          stats: { embeddings_created: embeddings },
        },
      ],
    });

    it('does not fire EMBEDDINGS_UPDATE on the first poll (no baseline)', async () => {
      list.mockResolvedValue(streamWith(5));
      service.addSubscriber();
      await flush();
      expect(emit).not.toHaveBeenCalledWith(SearchEvents.EMBEDDINGS_UPDATE);
    });

    it('fires EMBEDDINGS_UPDATE when the aggregate embedding count grows', async () => {
      list.mockResolvedValueOnce(streamWith(5));
      service.addSubscriber();
      await flush();

      list.mockResolvedValue(streamWith(9));
      jest.advanceTimersByTime(5000);
      await flush();
      expect(emit).toHaveBeenCalledWith(SearchEvents.EMBEDDINGS_UPDATE);
    });

    it('does not fire EMBEDDINGS_UPDATE when the count is unchanged', async () => {
      list.mockResolvedValue(streamWith(5));
      service.addSubscriber();
      await flush();

      emit.mockClear();
      jest.advanceTimersByTime(5000);
      await flush();
      expect(emit).not.toHaveBeenCalledWith(SearchEvents.EMBEDDINGS_UPDATE);
    });
  });
});
