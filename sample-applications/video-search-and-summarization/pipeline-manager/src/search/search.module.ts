// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { SearchStateService } from './services/search-state.service';
import { SearchController } from './controllers/search.controller';
import { SearchDbService } from './services/search-db.service';
import { TypeOrmModule } from '@nestjs/typeorm';
import { SearchEntity } from './model/search.entity';
import { SearchShimService } from './services/search-shim.service';
import { HttpModule } from '@nestjs/axios';
import { VideoUploadModule } from 'src/video-upload/video-upload.module';
import { FeaturesModule } from 'src/features/features.module';
import { SearchIndexVersionService } from './services/search-index-version.service';
import { SearchRefreshConfigService } from './services/search-refresh-config.service';
import { SearchConfigService } from './services/search-config.service';
import { SearchRefreshSchedulerService } from './services/search-refresh-scheduler.service';
import { DatastoreModule } from 'src/datastore/datastore.module';
import { SearchImageService } from './services/search-image.service';
import { SearchImageController } from './controllers/search-image.controller';

@Module({
  providers: [
    SearchStateService,
    SearchDbService,
    SearchShimService,
    SearchIndexVersionService,
    SearchRefreshConfigService,
    SearchConfigService,
    SearchRefreshSchedulerService,
    SearchImageService,
  ],
  // SearchImageController first so `search/images` is matched before the
  // `search/:queryId` routes.
  controllers: [SearchImageController, SearchController],
  imports: [
    HttpModule,
    TypeOrmModule.forFeature([SearchEntity]),
    VideoUploadModule,
    FeaturesModule,
    DatastoreModule,
  ],
  exports: [],
})
export class SearchModule {}
