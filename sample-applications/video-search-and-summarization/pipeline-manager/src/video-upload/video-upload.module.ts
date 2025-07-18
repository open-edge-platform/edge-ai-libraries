import { Module } from '@nestjs/common';
import { MulterModule } from '@nestjs/platform-express';
import { StateManagerModule } from 'src/state-manager/state-manager.module';
import { AppConfigService } from './services/app-config.service';
import { LanguageModelModule } from 'src/language-model/language-model.module';
import { VideoValidatorService } from './services/video-validator.service';
import { EvamModule } from 'src/evam/evam.module';
import { AudioModule } from 'src/audio/audio.module';
import { FeaturesService } from '../features/features.service';
import { VideoDbService } from './services/video-db.service';
import { VideoController } from './controllers/video.controller';
import { VideoService } from './services/video.service';
import { TypeOrmModule } from '@nestjs/typeorm';
import { VideoEntity } from './models/video.entity';
import { DatastoreModule } from 'src/datastore/datastore.module';
import { SearchModule } from 'src/search/search.module';
import { TagsService } from './services/tags.service';
import { TagsController } from './controllers/tags.controller';
import { TagsDbService } from './services/tags-db.service';
import { TagEntity } from './models/tags.entity';

@Module({
  providers: [
    AppConfigService,
    VideoValidatorService,
    FeaturesService,
    VideoDbService,
    VideoService,
    TagsService,
    TagsDbService,
  ],
  controllers: [VideoController, TagsController],
  exports: [AppConfigService, FeaturesService, VideoService, VideoDbService],
  imports: [
    StateManagerModule,
    LanguageModelModule,
    EvamModule,
    AudioModule,
    DatastoreModule,
    SearchModule,
    TypeOrmModule.forFeature([VideoEntity, TagEntity]),
    MulterModule.registerAsync({ useFactory: () => ({ dest: './data' }) }),
  ],
})
export class VideoUploadModule {}
