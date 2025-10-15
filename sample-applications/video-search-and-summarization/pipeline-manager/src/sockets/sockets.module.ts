// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { EventsGateway } from './events.gateway';
import { StateManagerModule } from 'src/state-manager/state-manager.module';

@Module({
  providers: [EventsGateway],
  exports: [EventsGateway],
  imports: [StateManagerModule],
})
export class SocketsModule {}
