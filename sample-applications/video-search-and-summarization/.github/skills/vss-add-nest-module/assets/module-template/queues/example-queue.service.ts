// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import { AppEvents } from 'src/events/app.events';

export interface ExampleQueueItem {
  exampleId: string;
}

@Injectable()
export class ExampleQueueService {
  waiting: ExampleQueueItem[] = [];
  processing: ExampleQueueItem[] = [];

  constructor(private $emitter: EventEmitter2) {}

  // Replace with a real enum value added to src/events/Pipeline.events.ts.
  // @OnEvent(ExampleEvents.PROCESS_TRIGGER)
  enqueue(item: ExampleQueueItem) {
    const alreadyQueued =
      this.waiting.some((el) => el.exampleId === item.exampleId) ||
      this.processing.some((el) => el.exampleId === item.exampleId);

    if (!alreadyQueued) {
      this.waiting.push(item);
    }
  }

  @OnEvent(AppEvents.FAST_TICK)
  processQueue() {
    if (this.waiting.length === 0) {
      return;
    }

    const nextItem = this.waiting.shift()!;
    this.processing.push(nextItem);

    try {
      // Do small dispatch work here, or call an injected service for the long-running operation.
      // this.$emitter.emit(ExampleEvents.PROCESS_COMPLETE, { exampleId: nextItem.exampleId });
    } finally {
      this.processing = this.processing.filter((el) => el.exampleId !== nextItem.exampleId);
    }
  }
}
