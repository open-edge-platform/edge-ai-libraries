// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import {} from 'amqplib';
import { AppModule } from './app.module';
import otelSDK from './tracing';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

async function bootstrap() {
  await otelSDK.start();

  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    cors: true,
  });

  // Raise the JSON body limit above the ~100kb default so base64 query images
  app.useBodyParser('json', { limit: '2mb' });
  app.useBodyParser('urlencoded', { limit: '2mb', extended: true });

  const config = new DocumentBuilder()
    .setTitle('Pipeline Manager')
    .setDescription('Pipeline Manager API')
    .setVersion('1.0')
    .addTag('pipeline')
    .addServer('/manager', 'Nginx manager prefix')
    .build();

  const documentFactory = () => SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('docs', app, documentFactory(), {
    jsonDocumentUrl: 'swagger/json',
    yamlDocumentUrl: 'swagger/yaml',
  });
  await app.init();

  await app.listen(process.env.PORT ?? 3000);
}
bootstrap();
