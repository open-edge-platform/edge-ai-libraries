// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AppEvents } from './events/app.events';
import { ConfigService } from '@nestjs/config';
import { TemplateService } from './language-model/services/template.service';
import { VideoDbService } from './video-upload/services/video-db.service';
import { StateService } from './state-manager/services/state.service';

@Injectable()
export class AppService {
  tickInterval: NodeJS.Timeout;
  fastTickInterval: NodeJS.Timeout;

  tickSpeed = 5_000;
  fastTick = 2_000;

  constructor(
    private $emitter: EventEmitter2,
    private $config: ConfigService,
    private $template: TemplateService,
    private $videoDB: VideoDbService,
    private $state: StateService,
  ) {
    this.startTicks();
    this.initStates();
  }

  private async initStates() {
    try {
      const videos = await this.$videoDB.readAll();
      await this.$state.init(videos);
      Logger.log('States Initialized!');
    } catch (error) {
      Logger.error('Error initializing states:', error);
    }
  }

  startTicks() {
    this.tickInterval = setInterval(() => {
      this.$emitter.emit(AppEvents.TICK);
    }, this.tickSpeed);

    this.fastTickInterval = setInterval(() => {
      this.$emitter.emit(AppEvents.FAST_TICK);
    }, this.fastTick);
  }

  stopTicks() {
    clearInterval(this.tickInterval);
    clearInterval(this.fastTickInterval);
  }
}
