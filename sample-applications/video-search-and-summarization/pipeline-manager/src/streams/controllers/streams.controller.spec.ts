// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadGatewayException,
  BadRequestException,
  NotFoundException,
  RequestTimeoutException,
  ServiceUnavailableException,
  ValidationPipe,
} from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AxiosError, AxiosResponse } from 'axios';
import { SearchEvents } from 'src/events/Pipeline.events';
import {
  LiveStreamBatchCreateDto,
  LiveStreamBatchDeleteDto,
  LiveStreamCreateDto,
  LiveStreamListQueryDto,
  LiveStreamUpdateDto,
} from '../models/stream.model';
import { StreamPollerService } from '../services/stream-poller.service';
import { StreamShimService } from '../services/stream-shim.service';
import { StreamsController } from './streams.controller';

const axiosErrorWithStatus = (status: number, detail?: string): AxiosError => {
  const error = new AxiosError('upstream failure');
  error.response = { status, data: detail ? { detail } : {} } as AxiosResponse;
  return error;
};

describe('StreamsController', () => {
  let controller: StreamsController;
  let shim: jest.Mocked<Partial<StreamShimService>>;
  let poller: jest.Mocked<Partial<StreamPollerService>>;
  let emit: jest.Mock;

  beforeEach(async () => {
    shim = {
      create: jest.fn(),
      createBatch: jest.fn(),
      list: jest.fn(),
      get: jest.fn(),
      update: jest.fn(),
      remove: jest.fn(),
      removeBatch: jest.fn(),
    };
    Object.defineProperty(shim, 'isConfigured', {
      value: true,
      configurable: true,
    });
    poller = { ensurePolling: jest.fn() };
    emit = jest.fn();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [StreamsController],
      providers: [
        { provide: StreamShimService, useValue: shim },
        { provide: StreamPollerService, useValue: poller },
        { provide: EventEmitter2, useValue: { emit } },
      ],
    }).compile();

    controller = module.get<StreamsController>(StreamsController);
  });

  describe('proxying', () => {
    it('forwards create to the shim', async () => {
      (shim.create as jest.Mock).mockResolvedValue({ stream: { id: 'a' } });
      const body = { stream_url: 'rtsp://cam/1' } as LiveStreamCreateDto;

      await expect(controller.create(body)).resolves.toEqual({
        stream: { id: 'a' },
      });
      expect(shim.create).toHaveBeenCalledWith(body);
      expect(poller.ensurePolling).toHaveBeenCalledTimes(1);
    });

    it('starts the poller after a successful create', async () => {
      (shim.create as jest.Mock).mockResolvedValue({ stream: { id: 'a' } });
      await controller.create({
        stream_url: 'rtsp://cam/1',
      } as LiveStreamCreateDto);
      expect(poller.ensurePolling).toHaveBeenCalledTimes(1);
    });

    it('does not start the poller when create fails', async () => {
      (shim.create as jest.Mock).mockRejectedValue(
        axiosErrorWithStatus(400),
      );
      await expect(
        controller.create({
          stream_url: 'rtsp://cam/1',
        } as LiveStreamCreateDto),
      ).rejects.toBeDefined();
      expect(poller.ensurePolling).not.toHaveBeenCalled();
    });

    it('forwards the purge flags on delete', async () => {
      (shim.remove as jest.Mock).mockResolvedValue({ stream_id: 'a' });
      await controller.remove('a', { purge_embeddings: true });
      expect(shim.remove).toHaveBeenCalledWith('a', { purge_embeddings: true });
    });

    it('re-runs watched queries when a delete purged embeddings', async () => {
      (shim.remove as jest.Mock).mockResolvedValue({
        stream_id: 'a',
        embeddings_purged: 12,
      });
      await controller.remove('a', { purge_embeddings: true });
      expect(emit).toHaveBeenCalledWith(SearchEvents.EMBEDDINGS_UPDATE);
    });

    it('does not re-run watched queries when a delete purged nothing', async () => {
      (shim.remove as jest.Mock).mockResolvedValue({
        stream_id: 'a',
        embeddings_purged: 0,
      });
      await controller.remove('a', {});
      expect(emit).not.toHaveBeenCalled();
    });

    it('re-runs watched queries when a batch delete purges embeddings', async () => {
      (shim.removeBatch as jest.Mock).mockResolvedValue({
        accepted: 2,
        rejected: 0,
        items: [],
      });
      await controller.removeBatch(
        { stream_ids: ['a', 'b'] } as never,
        { purge_embeddings: true },
      );
      expect(emit).toHaveBeenCalledWith(SearchEvents.EMBEDDINGS_UPDATE);
    });

    it('does not re-run watched queries when a batch delete keeps embeddings', async () => {
      (shim.removeBatch as jest.Mock).mockResolvedValue({
        accepted: 2,
        rejected: 0,
        items: [],
      });
      await controller.removeBatch({ stream_ids: ['a', 'b'] } as never, {});
      expect(emit).not.toHaveBeenCalled();
    });

    it('forwards list filters', async () => {
      (shim.list as jest.Mock).mockResolvedValue({ count: 0, streams: [] });
      const query = { tags: ['lobby'] } as LiveStreamListQueryDto;
      await controller.list(query);
      expect(shim.list).toHaveBeenCalledWith(query);
    });
  });

  describe('error mapping', () => {
    const cases: [number, unknown][] = [
      [400, BadRequestException],
      [422, BadRequestException],
      [404, NotFoundException],
      [503, ServiceUnavailableException],
      [500, BadGatewayException],
      [418, BadGatewayException],
    ];

    it.each(cases)('maps upstream %i', async (status, expected) => {
      (shim.get as jest.Mock).mockRejectedValue(
        axiosErrorWithStatus(status as number),
      );
      await expect(controller.get('a')).rejects.toBeInstanceOf(expected as never);
    });

    it('maps a timeout to 408', async () => {
      const error = new AxiosError('timeout');
      error.code = 'ECONNABORTED';
      (shim.get as jest.Mock).mockRejectedValue(error);
      await expect(controller.get('a')).rejects.toBeInstanceOf(
        RequestTimeoutException,
      );
    });

    it('maps a non-axios failure to 502', async () => {
      (shim.list as jest.Mock).mockRejectedValue(new Error('boom'));
      await expect(controller.list({})).rejects.toBeInstanceOf(
        BadGatewayException,
      );
    });

    it('surfaces the upstream detail for the concurrency cap', async () => {
      (shim.create as jest.Mock).mockRejectedValue(
        axiosErrorWithStatus(503, 'Maximum of 8 concurrent live streams'),
      );
      await expect(
        controller.create({ stream_url: 'rtsp://cam/1' } as LiveStreamCreateDto),
      ).rejects.toThrow('Maximum of 8 concurrent live streams');
    });

    it('explains an unconfigured deployment instead of reporting a gateway error', async () => {
      Object.defineProperty(shim, 'isConfigured', { value: false });
      (shim.list as jest.Mock).mockRejectedValue(new Error('ECONNREFUSED'));

      await expect(controller.list({})).rejects.toThrow(
        /no dataprep endpoint is configured/,
      );
    });

    it('never leaks the request body into the error message', async () => {
      (shim.create as jest.Mock).mockRejectedValue(
        new Error('connect failed rtsp://admin:hunter2@cam:554/s'),
      );
      const logSpy = jest
        .spyOn(controller['logger'], 'error')
        .mockImplementation(() => undefined);

      await expect(
        controller.create({
          stream_url: 'rtsp://admin:hunter2@cam:554/s',
        } as LiveStreamCreateDto),
      ).rejects.toThrow(/Live stream service error/);

      // The thrown message is generic...
      await expect(
        controller
          .create({ stream_url: 'rtsp://admin:hunter2@cam/s' } as LiveStreamCreateDto)
          .catch((e: Error) => {
            expect(e.message).not.toContain('hunter2');
            throw e;
          }),
      ).rejects.toBeDefined();

      logSpy.mockRestore();
    });
  });
});

describe('Live stream DTO validation', () => {
  const pipe = new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
  });

  const validate = (value: unknown, metatype: unknown) =>
    pipe.transform(value, {
      type: 'body',
      metatype: metatype as never,
    });

  describe('create', () => {
    it('accepts a minimal valid payload', async () => {
      await expect(
        validate({ stream_url: 'rtsp://cam:554/s' }, LiveStreamCreateDto),
      ).resolves.toMatchObject({ stream_url: 'rtsp://cam:554/s' });
    });

    it('accepts rtsps', async () => {
      await expect(
        validate({ stream_url: 'rtsps://cam:322/s' }, LiveStreamCreateDto),
      ).resolves.toBeDefined();
    });

    it.each([
      ['http://cam/s', 'wrong scheme'],
      ['file:///etc/passwd', 'file url'],
      ['/etc/passwd', 'bare path'],
      ['', 'empty'],
    ])('rejects %s (%s)', async (url) => {
      await expect(
        validate({ stream_url: url }, LiveStreamCreateDto),
      ).rejects.toThrow();
    });

    it('rejects a frame_interval outside 1-60', async () => {
      await expect(
        validate(
          { stream_url: 'rtsp://cam/s', frame_interval: 0 },
          LiveStreamCreateDto,
        ),
      ).rejects.toThrow();
      await expect(
        validate(
          { stream_url: 'rtsp://cam/s', frame_interval: 61 },
          LiveStreamCreateDto,
        ),
      ).rejects.toThrow();
    });

    it('rejects a detection_confidence outside 0.1-1.0', async () => {
      await expect(
        validate(
          { stream_url: 'rtsp://cam/s', detection_confidence: 1.5 },
          LiveStreamCreateDto,
        ),
      ).rejects.toThrow();
    });

    it('rejects an over-long stream_name', async () => {
      await expect(
        validate(
          { stream_url: 'rtsp://cam/s', stream_name: 'x'.repeat(257) },
          LiveStreamCreateDto,
        ),
      ).rejects.toThrow();
    });

    it('rejects an unknown field rather than forwarding it', async () => {
      await expect(
        validate(
          { stream_url: 'rtsp://cam/s', evil: 'payload' },
          LiveStreamCreateDto,
        ),
      ).rejects.toThrow();
    });
  });

  describe('batch create', () => {
    it('accepts a batch with at least one item', async () => {
      await expect(
        validate(
          { items: [{ stream_url: 'rtsp://cam:554/s' }] },
          LiveStreamBatchCreateDto,
        ),
      ).resolves.toMatchObject({ items: [{ stream_url: 'rtsp://cam:554/s' }] });
    });

    it('rejects an empty items array', async () => {
      // An empty batch is a client error (400), not a bad-gateway (502): the
      // DTO must reject it before it reaches the ingestion service.
      await expect(
        validate({ items: [] }, LiveStreamBatchCreateDto),
      ).rejects.toThrow();
    });

    it('rejects a batch item with a malformed url', async () => {
      await expect(
        validate(
          { items: [{ stream_url: 'http://cam/s' }] },
          LiveStreamBatchCreateDto,
        ),
      ).rejects.toThrow();
    });
  });

  describe('batch delete', () => {
    it('accepts a delete batch with at least one id', async () => {
      await expect(
        validate({ stream_ids: ['a'] }, LiveStreamBatchDeleteDto),
      ).resolves.toMatchObject({ stream_ids: ['a'] });
    });

    it('rejects an empty stream_ids array', async () => {
      // Same contract as batch create: an empty id list is a 400, not a 502.
      await expect(
        validate({ stream_ids: [] }, LiveStreamBatchDeleteDto),
      ).rejects.toThrow();
    });
  });

  describe('update', () => {
    it('allows a partial body', async () => {
      await expect(
        validate({ stream_name: 'lobby' }, LiveStreamUpdateDto),
      ).resolves.toEqual({ stream_name: 'lobby' });
    });

    it('allows an empty body', async () => {
      await expect(validate({}, LiveStreamUpdateDto)).resolves.toEqual({});
    });

    it.each(['running', 'paused'])('accepts state=%s', async (state) => {
      await expect(
        validate({ state }, LiveStreamUpdateDto),
      ).resolves.toEqual({ state });
    });

    it.each(['stopped', 'error', 'reconnecting', 'pending', 'starting'])(
      'rejects the non-caller-settable state %s',
      async (state) => {
        await expect(validate({ state }, LiveStreamUpdateDto)).rejects.toThrow();
      },
    );

    // dataprep's LiveStreamUpdateRequest has no stream_url field, so a URL
    // change is not expressible. forbidNonWhitelisted makes that a visible 400
    // rather than a silently discarded edit.
    it('rejects an attempt to change stream_url', async () => {
      await expect(
        validate({ stream_url: 'rtsp://other/s' }, LiveStreamUpdateDto),
      ).rejects.toThrow();
    });
  });
});
