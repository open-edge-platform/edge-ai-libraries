// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import Connection, { Consumer } from 'rabbitmq-client';
import { ChunkQueue } from '../models/message-broker.model';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { ConfigService } from '@nestjs/config';

import { inspect } from 'util';
import { FeaturesService } from 'src/features/features.service';

@Injectable()
export class RabbitmqService {
  connection: Connection;

  rabbitConnection: Connection;

  consumer: Consumer;

  constructor(
    private $emitter: EventEmitter2,
    private $config: ConfigService,
    private $feature: FeaturesService,
  ) {
    if (this.$feature.hasFeature('summary')) {
      this.connect();
    }
  }

  connect() {
    const rmqHost: string = this.$config.get('rmq.host')!;
    const rmqUser: string = this.$config.get('rmq.username')!;
    const rmqPass: string = this.$config.get('rmq.password')!;
    const rmqPort: number = this.$config.get('rmq.amqpPort')!;

    console.log(rmqHost, rmqUser, rmqPass);

    this.rabbitConnection = new Connection(
      `amqp://${rmqUser}:${rmqPass}@${rmqHost}:${rmqPort}`,
    );

    this.rabbitConnection.on('error', (error) => {
      console.log('ERROR', error);
    });

    const queueName: string = this.$config.get('evam.rmq.queue')!;
    const exchange: string = this.$config.get('evam.rmq.exchange')!;
    let routingKey: string = this.$config.get('evam.videoTopic')!;

    routingKey = routingKey.replaceAll('/', '.');

    this.startListeners(queueName, exchange, routingKey);
  }

  startListeners(queue: string, exchange: string, routingKey: string) {
    if (this.rabbitConnection) {
      this.consumer = this.rabbitConnection.createConsumer(
        {
          queue,
          queueOptions: { durable: true },
          qos: { prefetchCount: 1 },
          exchanges: [{ exchange, type: 'topic', durable: true }],
          queueBindings: [{ exchange, routingKey }],
        },
        (msg) => {
          console.log('Message received', msg);
          const chunkData: ChunkQueue = JSON.parse(msg.body.toString());
          // console.log('CHUNK DATA', inspect(chunkData, false, null, true));
          this.$emitter.emit(PipelineEvents.CHUNK_RECEIVED, chunkData);
        },
      );

      this.consumer.on('error', (error) => {
        console.log('Consumer error', error);
      });
    }
  }
}
