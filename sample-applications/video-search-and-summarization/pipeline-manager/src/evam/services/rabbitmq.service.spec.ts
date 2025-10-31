// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { RabbitmqService } from './rabbitmq.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ConfigService } from '@nestjs/config';
import { PipelineEvents } from '../../events/Pipeline.events';
import Connection, { Consumer } from 'rabbitmq-client';
import { FeaturesService } from 'src/features/features.service';

// Create mocks
jest.mock('rabbitmq-client', () => {
  const consumerOnMock = jest.fn();
  const consumerMock = { on: consumerOnMock };
  const createConsumerMock = jest.fn().mockReturnValue(consumerMock);
  const connectionOnMock = jest.fn();

  return {
    __esModule: true,
    default: jest.fn().mockImplementation(() => ({
      on: connectionOnMock,
      createConsumer: createConsumerMock,
    })),
  };
});

describe('RabbitmqService', () => {
  let service: RabbitmqService;
  let configService: ConfigService;
  let eventEmitter: EventEmitter2;
  let mockConnection;
  let mockConsumer;

  // Mock config values
  const mockConfig = {
    'rmq.host': 'localhost',
    'rmq.amqpPort': 5672,
    'rmq.username': 'guest',
    'rmq.password': 'guest',
    'evam.rmq.queue': 'test-queue',
    'evam.rmq.exchange': 'test-exchange',
    'evam.videoTopic': 'video/topic',
  };

  beforeEach(async () => {
    // Reset mock implementations before each test
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        RabbitmqService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => mockConfig[key]),
          },
        },
        {
          provide: EventEmitter2,
          useValue: {
            emit: jest.fn(),
          },
        },
        {
          provide: FeaturesService,
          useValue: {
            hasFeature: jest.fn().mockReturnValue(true),
          },
        },
      ],
    }).compile();

    service = module.get<RabbitmqService>(RabbitmqService);
    configService = module.get<ConfigService>(ConfigService);
    eventEmitter = module.get<EventEmitter2>(EventEmitter2);
    mockConnection = service.rabbitConnection;
    mockConsumer = service.consumer;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('connect', () => {
    it('should create a connection with correct configuration', () => {
      // Reset connection to test connect method
      service.rabbitConnection;

      // Call connect method
      service.connect();

      // Verify connection was created with correct URL
      expect(Connection).toHaveBeenCalledWith(
        `amqp://${mockConfig['rmq.username']}:${mockConfig['rmq.password']}@${mockConfig['rmq.host']}:${mockConfig['rmq.amqpPort']}`,
      );

      // Verify event listener was added
      expect(service.rabbitConnection.on).toHaveBeenCalledWith(
        'error',
        expect.any(Function),
      );

      // Verify startListeners was called with correct params
      expect(service.consumer).toBeDefined();
    });

    it('should handle connection errors', () => {
      // Setup spy on console.log
      const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();

      // Get the error handler function
      const connectionOnMock = service.rabbitConnection.on as jest.Mock;
      const errorHandler = connectionOnMock.mock.calls.find(
        (call) => call[0] === 'error',
      )[1];

      // Test the error handler
      const testError = new Error('Connection failed');
      errorHandler(testError);

      expect(consoleLogSpy).toHaveBeenCalledWith('ERROR', testError);

      consoleLogSpy.mockRestore();
    });
  });

  describe('startListeners', () => {
    it('should create a consumer with correct parameters', () => {
      const queue = 'test-queue';
      const exchange = 'test-exchange';
      const routingKey = 'test.routing.key';

      // Call method directly to test
      service.startListeners(queue, exchange, routingKey);

      // Verify consumer creation
      expect(mockConnection.createConsumer).toHaveBeenCalledWith(
        {
          queue,
          queueOptions: { durable: true },
          qos: { prefetchCount: 1 },
          exchanges: [{ exchange, type: 'topic', durable: true }],
          queueBindings: [{ exchange, routingKey }],
        },
        expect.any(Function),
      );

      // Verify error handler
      expect(service.consumer.on).toHaveBeenCalledWith(
        'error',
        expect.any(Function),
      );
    });

    it('should handle consumer errors', () => {
      // Setup spy on console.log
      const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();

      // Get the error handler function
      const consumerOnMock = service.consumer.on as jest.Mock;
      const errorHandler = consumerOnMock.mock.calls.find(
        (call) => call[0] === 'error',
      )[1];

      // Test the error handler
      const testError = new Error('Consumer failed');
      errorHandler(testError);

      expect(consoleLogSpy).toHaveBeenCalledWith('Consumer error', testError);

      consoleLogSpy.mockRestore();
    });

    it('should not create a consumer if connection is not available', () => {
      // Set connection to null
      service.rabbitConnection = null as any;
      service.consumer = undefined as any;

      // Call method
      service.startListeners('queue', 'exchange', 'routing');

      // Consumer should not be created
      expect(service.consumer).toBeUndefined();
    });
  });

  describe('message handling', () => {
    it('should emit event when message is received', () => {
      // Mock data
      const mockChunkData = {
        evamIdentifier: 'test-123',
        chunkId: 42,
        frames: [
          {
            frameId: 'frame-1',
            imageUri: 'image/uri',
            metadata: {
              frame_timestamp: 123456,
              image_format: 'jpg',
            },
          },
        ],
      };

      // Get the message handler function
      const createConsumerMock = mockConnection.createConsumer as jest.Mock;
      const messageHandler = createConsumerMock.mock.calls[0][1];

      // Create a mock message
      const mockMessage = {
        body: Buffer.from(JSON.stringify(mockChunkData)),
      };

      // Setup spy on console.log
      const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();

      // Call the message handler
      messageHandler(mockMessage);

      // Verify event was emitted
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.CHUNK_RECEIVED,
        mockChunkData,
      );

      // Verify logging
      expect(consoleLogSpy).toHaveBeenCalledWith(
        'Message received',
        mockMessage,
      );

      consoleLogSpy.mockRestore();
    });

    it('should handle malformed JSON in message body', () => {
      // Get the message handler function
      const createConsumerMock = mockConnection.createConsumer as jest.Mock;
      const messageHandler = createConsumerMock.mock.calls[0][1];

      // Create a mock message with invalid JSON
      const mockMessage = {
        body: Buffer.from('invalid json'),
      };

      // Setup spy on console.log
      const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();

      // Expect the handler to throw
      expect(() => {
        messageHandler(mockMessage);
      }).toThrow(SyntaxError);

      // Verify event was not emitted
      expect(eventEmitter.emit).not.toHaveBeenCalled();

      consoleLogSpy.mockRestore();
    });
  });

  describe('constructor', () => {
    it('should call connect method when instantiated', () => {
      // Create a new instance with connect method spied
      const connectSpy = jest
        .spyOn(RabbitmqService.prototype, 'connect')
        .mockImplementation();
      
      const mockFeaturesService = {
        hasFeature: jest.fn().mockReturnValue(true),
      };
      
      const testService = new RabbitmqService(
        eventEmitter as any,
        configService as any,
        mockFeaturesService as any,
      );

      expect(connectSpy).toHaveBeenCalled();

      connectSpy.mockRestore();
    });
  });
});
