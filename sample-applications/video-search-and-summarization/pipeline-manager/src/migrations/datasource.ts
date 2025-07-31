// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { SearchEntity } from 'src/search/model/search.entity';
import { StateEntity } from 'src/state-manager/models/state.entity';
import { TagEntity } from 'src/video-upload/models/tags.entity';
import { VideoEntity } from 'src/video-upload/models/video.entity';
import { DataSource } from 'typeorm';

export default new DataSource({
  type: 'postgres',
  host: process.env.DB_HOST,
  port: +process.env.DB_PORT!,
  username: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  entities: [StateEntity, VideoEntity, SearchEntity, TagEntity],
  migrations: ['src/migrations/*.ts'],
  migrationsTableName: 'vss_migrations',
});
