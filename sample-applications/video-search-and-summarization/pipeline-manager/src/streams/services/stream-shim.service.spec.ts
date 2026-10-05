// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import axios from 'axios';
import { of } from 'rxjs';
import { LiveStreamState } from '../models/stream.model';
import { StreamShimService } from './stream-shim.service';

const ENDPOINT = 'http://multimodal-dataprep:8000';

describe('StreamShimService', () => {
  let service: StreamShimService;
  let http: {
    get: jest.Mock;
    post: jest.Mock;
    patch: jest.Mock;
    delete: jest.Mock;
  };
  let configValues: Record<string, unknown>;

  const ok = (data: unknown) => of({ data });

  beforeEach(async () => {
    http = {
      get: jest.fn().mockReturnValue(ok({ count: 0, streams: [] })),
      post: jest.fn().mockReturnValue(ok({ stream: {} })),
      patch: jest.fn().mockReturnValue(ok({ stream: {} })),
      delete: jest.fn().mockReturnValue(ok({ stream_id: 'abc' })),
    };
    configValues = {
      'streams.endpoint': ENDPOINT,
      'streams.timeoutMs': 15000,
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        StreamShimService,
        {
          provide: ConfigService,
          useValue: { get: jest.fn((key: string) => configValues[key]) },
        },
        { provide: HttpService, useValue: http },
      ],
    }).compile();

    service = module.get<StreamShimService>(StreamShimService);
  });

  describe('URL construction', () => {
    it('targets the bare /media/streams path', async () => {
      await service.list();
      expect(http.get).toHaveBeenCalledWith(
        `${ENDPOINT}/media/streams`,
        expect.anything(),
      );
    });

    it('appends the stream id for single-resource routes', async () => {
      await service.get('stream-1');
      expect(http.get.mock.calls[0][0]).toBe(
        `${ENDPOINT}/media/streams/stream-1`,
      );

      await service.update('stream-1', { stream_name: 'lobby' });
      expect(http.patch.mock.calls[0][0]).toBe(
        `${ENDPOINT}/media/streams/stream-1`,
      );

      await service.remove('stream-1');
      expect(http.delete.mock.calls[0][0]).toBe(
        `${ENDPOINT}/media/streams/stream-1`,
      );
    });

    it('encodes a stream id so it cannot escape the path', async () => {
      await service.get('../../health');
      expect(http.get.mock.calls[0][0]).toBe(
        `${ENDPOINT}/media/streams/..%2F..%2Fhealth`,
      );
    });

    it('does not double a trailing slash on the endpoint', async () => {
      configValues['streams.endpoint'] = `${ENDPOINT}/`;
      await service.list();
      expect(http.get.mock.calls[0][0]).toBe(`${ENDPOINT}/media/streams`);
    });

    it('uses /batch for bulk create', async () => {
      await service.createBatch({ items: [{ stream_url: 'rtsp://a/1' }] });
      expect(http.post.mock.calls[0][0]).toBe(
        `${ENDPOINT}/media/streams/batch`,
      );
    });
  });

  describe('query serialization', () => {
    // FastAPI binds List[str] from repeated keys. Axios' default array
    // serializer emits `tags[]=a`, which FastAPI ignores silently - the filter
    // would appear to work while returning unfiltered results.
    it('serializes multiple tags as repeated unbracketed keys', async () => {
      await service.list({ tags: ['lobby', 'floor-2'] });

      const config = http.get.mock.calls[0][1];
      const serialized = axios.getUri({
        url: '/x',
        params: config.params,
        paramsSerializer: config.paramsSerializer,
      });

      expect(serialized).toContain('tags=lobby');
      expect(serialized).toContain('tags=floor-2');
      expect(serialized).not.toContain('tags[]');
      expect(serialized).not.toContain('tags%5B%5D');
      expect(serialized).not.toMatch(/tags(%5B|\[)0/);
    });

    it('omits absent filters rather than sending empty values', async () => {
      await service.list({});
      expect(http.get.mock.calls[0][1].params).toEqual({});
    });

    it('passes the state filter through', async () => {
      await service.list({ state: LiveStreamState.ERROR });
      expect(http.get.mock.calls[0][1].params).toEqual({ state: 'error' });
    });
  });

  describe('purge flags', () => {
    it('defaults both purge flags to false', async () => {
      await service.remove('stream-1');
      expect(http.delete.mock.calls[0][1].params).toEqual({
        purge_embeddings: false,
        purge_media: false,
      });
    });

    it('forwards purge flags on single delete', async () => {
      await service.remove('stream-1', {
        purge_embeddings: true,
        purge_media: true,
      });
      expect(http.delete.mock.calls[0][1].params).toEqual({
        purge_embeddings: true,
        purge_media: true,
      });
    });

    it('forwards purge flags on batch delete, with ids in the body', async () => {
      await service.removeBatch({ stream_ids: ['a', 'b'] }, { purge_media: true });

      const [, config] = http.delete.mock.calls[0];
      expect(config.params).toEqual({
        purge_embeddings: false,
        purge_media: true,
      });
      expect(config.data).toEqual({ stream_ids: ['a', 'b'] });
    });
  });

  describe('configuration', () => {
    it('reports unconfigured when no endpoint is set', () => {
      configValues['streams.endpoint'] = '';
      expect(service.isConfigured).toBe(false);
    });

    it('applies the configured timeout', async () => {
      configValues['streams.timeoutMs'] = 1234;
      await service.list();
      expect(http.get.mock.calls[0][1].timeout).toBe(1234);
    });
  });

  describe('credential safety', () => {
    it('never writes the request body to the logger', async () => {
      const spy = jest
        .spyOn(service['logger'], 'log')
        .mockImplementation(() => undefined);

      await service.create({ stream_url: 'rtsp://admin:hunter2@cam:554/s' });

      for (const call of spy.mock.calls) {
        expect(JSON.stringify(call)).not.toContain('hunter2');
        expect(JSON.stringify(call)).not.toContain('admin');
      }
      spy.mockRestore();
    });
  });
});
