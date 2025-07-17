import { Module } from '@nestjs/common';
import { DataPrepShimService } from './services/data-prep-shim.service';
import { ConfigModule } from '@nestjs/config';
import { HttpModule } from '@nestjs/axios';

@Module({
  providers: [DataPrepShimService],
  imports: [ConfigModule, HttpModule],
  exports: [DataPrepShimService],
})
export class DataPrepModule {}
