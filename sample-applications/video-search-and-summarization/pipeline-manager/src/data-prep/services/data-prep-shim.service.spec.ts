// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { DataPrepShimService } from './data-prep-shim.service';
import { ConfigService } from '@nestjs/config';
import { HttpService } from '@nestjs/axios';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AxiosError } from 'axios';
import { lastValueFrom, of, throwError } from 'rxjs';

describe('DataPrepShimService', () => {
  let service: DataPrepShimService;
  let httpGet: jest.Mock;
  let eventEmit: jest.Mock;

  beforeEach(async () => {
    httpGet = jest.fn();
    eventEmit = jest.fn();
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        DataPrepShimService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config = {
                'search.dataPrep': 'http://localhost:8080/dataprep',
                'search.dataPrepTimeoutMs': 600000,
                'search.dataPrepPollMaxRetries': 2,
                'search.dataPrepPollTimeoutMs': 10000,
                'search.dataPrepPollRetryDelayMs': 0,
              };
              return config[key];
            }),
          },
        },
        {
          provide: HttpService,
          useValue: {
            post: jest.fn(),
            get: httpGet,
          },
        },
        {
          provide: EventEmitter2,
          useValue: {
            emit: eventEmit,
          },
        },
      ],
    }).compile();

    service = module.get<DataPrepShimService>(DataPrepShimService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('retries ECONNRESET while polling and returns the recovered status', async () => {
    const reset = new AxiosError('read ECONNRESET', 'ECONNRESET');
    const completed = {
      data: { state: 'completed', completed: 2, failed: 0 },
    } as any;
    httpGet
      .mockReturnValueOnce(throwError(() => reset))
      .mockReturnValueOnce(of(completed));

    await expect(
      lastValueFrom(service.getBatchJobStatus('job-1')),
    ).resolves.toBe(completed);
    expect(httpGet).toHaveBeenCalledTimes(2);
    expect(httpGet).toHaveBeenLastCalledWith(
      'http://localhost:8080/dataprep/media/jobs/job-1',
      { timeout: 10000 },
    );
    expect(eventEmit).toHaveBeenCalledTimes(1);
  });

  it.each([502, 503, 504])(
    'retries transient HTTP %i responses while polling',
    async (status) => {
      const transientError = new AxiosError(
        `Request failed with status code ${status}`,
        'ERR_BAD_RESPONSE',
        undefined,
        undefined,
        {
          status,
          statusText: 'Transient upstream failure',
          headers: {},
          config: { headers: {} } as any,
          data: {},
        },
      );
      const running = {
        data: { state: 'running', completed: 0, failed: 0 },
      } as any;
      httpGet
        .mockReturnValueOnce(throwError(() => transientError))
        .mockReturnValueOnce(of(running));

      await expect(
        lastValueFrom(service.getBatchJobStatus('job-1')),
      ).resolves.toBe(running);
      expect(httpGet).toHaveBeenCalledTimes(2);
    },
  );

  it('returns a transient error after exhausting the retry budget', async () => {
    const reset = new AxiosError('read ECONNRESET', 'ECONNRESET');
    httpGet.mockReturnValue(throwError(() => reset));

    await expect(
      lastValueFrom(service.getBatchJobStatus('job-1')),
    ).rejects.toBe(reset);
    expect(httpGet).toHaveBeenCalledTimes(3);
  });

  it('does not retry non-transient HTTP responses', async () => {
    const badRequest = new AxiosError(
      'Request failed with status code 400',
      'ERR_BAD_REQUEST',
      undefined,
      undefined,
      {
        status: 400,
        statusText: 'Bad Request',
        headers: {},
        config: { headers: {} } as any,
        data: {},
      },
    );
    httpGet.mockReturnValue(throwError(() => badRequest));

    await expect(
      lastValueFrom(service.getBatchJobStatus('job-1')),
    ).rejects.toBe(badRequest);
    expect(httpGet).toHaveBeenCalledTimes(1);
  });
});
