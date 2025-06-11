import { NestFactory } from '@nestjs/core';
import {} from 'amqplib';
import { AppModule } from './app.module';
import otelSDK from './tracing';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

async function bootstrap() {
  otelSDK.start();

  const app = await NestFactory.create(AppModule, { cors: true });

  const config = new DocumentBuilder()
    .setTitle('Pipeline Manager')
    .setDescription('Pipeline Manager API')
    .setVersion('1.0')
    .addTag('pipeline')
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
