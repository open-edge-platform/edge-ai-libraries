// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Injectable } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AppEvents } from './events/app.events';
import { SystemConfig } from './video-upload/models/upload.model';
import { ConfigService } from '@nestjs/config';
import { TemplateService } from './language-model/services/template.service';

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
  ) {
    this.startTicks();
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
