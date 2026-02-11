// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { StateManagerModule } from './state-manager/state-manager.module';
import { VideoUploadModule } from './video-upload/video-upload.module';
import { DatastoreModule } from './datastore/datastore.module';
import { LanguageModelModule } from './language-model/language-model.module';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { EvamModule } from './evam/evam.module';
import { SocketsModule } from './sockets/sockets.module';
import { ConfigModule } from '@nestjs/config';
import configuration from './config/configuration';
import { TypeOrmModule } from '@nestjs/typeorm';
import { StateEntity } from './state-manager/models/state.entity';
import { AudioModule } from './audio/audio.module';
import { OpenTelemetryModule } from 'nestjs-otel';
import { VideoEntity } from './video-upload/models/video.entity';
import { SearchModule } from './search/search.module';
import { SearchEntity } from './search/model/search.entity';
import { TagEntity } from './video-upload/models/tags.entity';
import { SummaryModule } from './summary/summary.module';
import { HealthModule } from './health/health.module';
import { DataPrepModule } from './data-prep/data-prep.module';
import { TelemetryModule } from './telemetry/telemetry.module';

const OpenTelemetryModuleConfig = OpenTelemetryModule.forRoot({
  metrics: {
    hostMetrics: true, // Includes Host Metrics
    apiMetrics: {
      enable: true, // Includes api metrics
      defaultAttributes: {
        // You can set default labels for api metrics
        custom: 'label',
      },
      ignoreRoutes: ['/favicon.ico'], // You can ignore specific routes (See https://docs.nestjs.com/middleware#excluding-routes for options)
      ignoreUndefinedRoutes: false, //Records metrics for all URLs, even undefined ones
      prefix: 'my_prefix', // Add a custom prefix to all API metrics
    },
  },
});

@Module({
  imports: [
    OpenTelemetryModuleConfig,
    StateManagerModule,
    VideoUploadModule,
    DatastoreModule,
    LanguageModelModule,
    EventEmitterModule.forRoot({ delimiter: '.', maxListeners: 5 }),
    EvamModule,
    SocketsModule,
    ConfigModule.forRoot({ load: [configuration], isGlobal: true }),
    TypeOrmModule.forRoot({
      type: 'postgres',
      host: process.env.DB_HOST,
      port: parseInt(process.env.DB_PORT ?? '', 10),
      username: process.env.DB_USER,
      password: process.env.DB_PASSWORD,
      database: process.env.DB_NAME,
      entities: [StateEntity, VideoEntity, SearchEntity, TagEntity],
      migrations: ['./migrations/*.ts'],
      migrationsRun: true,
      synchronize: true,
    }),
    AudioModule,
    SearchModule,
    SummaryModule,
    HealthModule,
    DataPrepModule,
    TelemetryModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
