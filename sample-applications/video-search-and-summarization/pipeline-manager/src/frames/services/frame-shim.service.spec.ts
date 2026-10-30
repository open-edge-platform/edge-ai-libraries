// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import { of } from 'rxjs';
import { FrameShimService } from './frame-shim.service';

const ENDPOINT = 'http://multimodal-dataprep:8000';

describe('FrameShimService', () => {
  let service: FrameShimService;
  let http: { get: jest.Mock };
  let configValues: Record<string, unknown>;

  const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0]);

  const axiosOk = (data: Buffer, headers: Record<string, string>) =>
    of({
      data: data.buffer.slice(
        data.byteOffset,
        data.byteOffset + data.byteLength,
      ),
      headers,
    });

  beforeEach(async () => {
    http = {
      get: jest
        .fn()
        .mockReturnValue(
          axiosOk(jpeg, {
            'content-type': 'image/jpeg',
            'x-frame-width': '640',
            'x-frame-height': '480',
            'x-frame-variant': 'full',
            'cache-control': 'no-store',
          }),
        ),
    };
    configValues = {
      'search.dataPrep': ENDPOINT,
      'search.dataPrepTimeoutMs': 30000,
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        FrameShimService,
        {
          provide: ConfigService,
          useValue: { get: jest.fn((key: string) => configValues[key]) },
        },
        { provide: HttpService, useValue: http },
      ],
    }).compile();

    service = module.get<FrameShimService>(FrameShimService);
  });

  it('targets dataprep /media/frame with arraybuffer response type', async () => {
    await service.getFrame({ video_id: 'vid1', timestamp: 2.5 });
    expect(http.get).toHaveBeenCalledWith(
      `${ENDPOINT}/media/frame`,
      expect.objectContaining({ responseType: 'arraybuffer' }),
    );
  });

  it('forwards only the provided query params', async () => {
    await service.getFrame({
      video_id: 'vid1',
      timestamp: 4,
      variant: 'crop',
      crop_bbox: '1,2,3,4',
      format: 'json',
      quality: 80,
    });
    const params = http.get.mock.calls[0][1].params;
    expect(params).toEqual({
      video_id: 'vid1',
      timestamp: 4,
      variant: 'crop',
      crop_bbox: '1,2,3,4',
      format: 'json',
      quality: 80,
    });
    expect(params).not.toHaveProperty('media_path');
    expect(params).not.toHaveProperty('bucket_name');
  });

  it('returns the body, content type, and relayed frame headers', async () => {
    const result = await service.getFrame({ video_id: 'vid1', timestamp: 0 });
    expect(Buffer.isBuffer(result.body)).toBe(true);
    expect(result.body.equals(jpeg)).toBe(true);
    expect(result.contentType).toBe('image/jpeg');
    expect(result.frameHeaders).toMatchObject({
      'x-frame-width': '640',
      'x-frame-height': '480',
      'x-frame-variant': 'full',
      'cache-control': 'no-store',
    });
  });

  it('isConfigured reflects the dataprep endpoint presence', () => {
    expect(service.isConfigured).toBe(true);
    configValues['search.dataPrep'] = '';
    expect(service.isConfigured).toBe(false);
  });
});
