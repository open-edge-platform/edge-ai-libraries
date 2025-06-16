import { Module } from '@nestjs/common';
import { SummaryController } from './controllers/summary.controller';
import { VideoUploadModule } from 'src/video-upload/video-upload.module';
import { StateManagerModule } from 'src/state-manager/state-manager.module';

@Module({
  imports: [VideoUploadModule, StateManagerModule],
  controllers: [SummaryController],
  providers: [],
})
export class PipelineModule {}
