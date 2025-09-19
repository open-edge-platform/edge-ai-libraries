// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { DatastoreService } from './services/datastore.service';
import { HttpModule, HttpModuleOptions } from '@nestjs/axios';
import { ConfigModule, ConfigService } from '@nestjs/config';
import axios, { InternalAxiosRequestConfig } from 'axios';
import { LocalstoreService } from './services/localstore.service';

@Module({
  imports: [
    ConfigModule,
    HttpModule.registerAsync({
      imports: [ConfigModule],
      useFactory: (configService: ConfigService) =>
        createHttpModuleOptions(configService),
      inject: [ConfigService],
    }),
  ],
  providers: [DatastoreService, LocalstoreService],
  exports: [DatastoreService, LocalstoreService],
})
export class DatastoreModule {}

function createHttpModuleOptions(
  configService: ConfigService,
): HttpModuleOptions {
  let proxyHost = configService.get<string>('PROXY_HOST');
  let proxyPort = configService.get<number>('PROXY_PORT');
  let proxyProtocol = configService.get<string>('PROXY_PROTOCOL') || 'http';
  const noProxy = configService.get<string>('NO_PROXY');
  const proxyUrl = configService.get<string>('PROXY_URL');

  // If proxy is provided in form of PROXY_URL
  if (!proxyHost && !proxyPort && proxyUrl) {
    let url: URL;
    try {
      url = new URL(proxyUrl);
      proxyHost = url.hostname;
      proxyPort = parseInt(url.port, 10);
      proxyProtocol = url.protocol.slice(0, -1); // remove trailing ':'
    } catch (error) {
      throw new Error(`Invalid proxy URL: ${proxyUrl}\n${error}`);
    }
  }
  const axiosInstance = axios.create();

  axiosInstance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      // Add custom headers
      config.headers['User-Agent'] = 'VideoSummarizationApp/1.0';

      // Handle proxy settings
      if (proxyHost && proxyPort && proxyProtocol) {
        const url = new URL(config.url || '');
        if (noProxy && noProxy.split(',').includes(url.hostname)) {
          config.proxy = false;
        } else {
          config.proxy = {
            host: proxyHost,
            port: proxyPort,
            protocol: proxyProtocol,
          };
        }
      }
      return config;
    },
  );

  return {
    httpAgent: axiosInstance.defaults.httpAgent,
    httpsAgent: axiosInstance.defaults.httpsAgent,
  };
}
