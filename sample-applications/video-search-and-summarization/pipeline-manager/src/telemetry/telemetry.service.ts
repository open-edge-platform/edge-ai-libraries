// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { HttpAdapterHost } from '@nestjs/core';
import { IncomingMessage } from 'http';
import { Socket } from 'net';
import { WebSocket, WebSocketServer } from 'ws';

type RawMessage = string | Buffer | ArrayBuffer | Buffer[];

@Injectable()
export class TelemetryService implements OnModuleInit, OnModuleDestroy {
  private static readonly COLLECTOR_PATH = '/metrics/ws/collector';
  private static readonly CLIENTS_PATH = '/metrics/ws/clients';
  private static readonly DISCONNECT_LOG_INTERVAL_MS = 15000;

  private collectorServer?: WebSocketServer;
  private clientsServer?: WebSocketServer;
  private collectorSocket: WebSocket | null = null;
  private clientSockets = new Set<WebSocket>();
  private upgradeHandler?: (request: IncomingMessage, socket: Socket, head: Buffer) => void;
  private collectorConnected = false;
  private lastCollectorDisconnectLogAt = 0;
  private readonly logger = new Logger(TelemetryService.name);

  constructor(private readonly httpAdapterHost: HttpAdapterHost) {}

  onModuleInit(): void {
    const httpServer = this.httpAdapterHost.httpAdapter.getHttpServer();

    this.collectorServer = new WebSocketServer({
      noServer: true,
      perMessageDeflate: false,
    });
    this.clientsServer = new WebSocketServer({
      noServer: true,
      perMessageDeflate: false,
    });

    this.collectorServer.on('connection', (socket) => this.handleCollectorConnection(socket));
    this.clientsServer.on('connection', (socket) => this.handleClientConnection(socket));

    this.upgradeHandler = (request, socket, head) => {
      const url = request.url ?? '';
      let pathname = '';
      try {
        pathname = new URL(url, 'http://localhost').pathname;
      } catch (err) {
        this.logger.warn(`Failed to parse telemetry upgrade URL: ${err}`);
      }

      if (pathname === TelemetryService.COLLECTOR_PATH && this.collectorServer) {
        this.collectorServer.handleUpgrade(request, socket, head, (ws) => {
          this.collectorServer?.emit('connection', ws, request);
        });
        return;
      }

      if (pathname === TelemetryService.CLIENTS_PATH && this.clientsServer) {
        this.clientsServer.handleUpgrade(request, socket, head, (ws) => {
          this.clientsServer?.emit('connection', ws, request);
        });
        return;
      }
    };

    httpServer.prependListener('upgrade', this.upgradeHandler);

    this.logger.log('Telemetry WebSocket endpoints ready at /metrics/ws/*');
  }

  onModuleDestroy(): void {
    const httpServer = this.httpAdapterHost.httpAdapter.getHttpServer();
    if (this.upgradeHandler) {
      httpServer.off('upgrade', this.upgradeHandler);
    }

    this.collectorSocket?.removeAllListeners();
    this.collectorSocket?.close();
    this.collectorSocket = null;

    this.clientSockets.forEach((client) => {
      client.removeAllListeners();
      client.close();
    });
    this.clientSockets.clear();

    this.collectorServer?.close();
    this.clientsServer?.close();
  }

  getStatus(): { collectorConnected: boolean; clientsConnected: number } {
    const clientsConnected = Array.from(this.clientSockets).filter(
      (client) => client.readyState === WebSocket.OPEN,
    ).length;

    const collectorConnected =
      !!this.collectorSocket && this.collectorSocket.readyState === WebSocket.OPEN;

    return { collectorConnected, clientsConnected };
  }

  private handleCollectorConnection(socket: WebSocket): void {
    if (this.collectorSocket && this.collectorSocket.readyState === WebSocket.OPEN) {
      this.logger.warn('Rejecting collector connection: an active collector already exists.');
      socket.send(JSON.stringify({ error: 'Collector already connected; only one allowed.' }));
      socket.close(1008, 'Collector already connected');
      return;
    }

    this.collectorSocket = socket;
    if (!this.collectorConnected) {
      this.logger.log('Collector connected');
    }
    this.collectorConnected = true;

    socket.on('message', (data) => this.handleCollectorMessage(data));
    socket.on('close', (code, reason) => this.handleCollectorClose(socket, code, reason));
    socket.on('error', (err) => {
      this.logger.warn(`Collector socket error: ${err}`);
    });

    socket.on('ping', (data) => {
      try {
        socket.pong(data);
      } catch (err) {
        this.logger.warn(`Failed to respond to collector ping: ${err}`);
      }
    });
  }

  private handleCollectorClose(socket: WebSocket, code?: number, reason?: Buffer): void {
    if (this.collectorSocket !== socket) {
      return;
    }

    this.collectorSocket = null;
    this.collectorConnected = false;

    const reasonText = reason && reason.length ? reason.toString('utf-8') : 'no reason provided';
    const now = Date.now();
    if (now - this.lastCollectorDisconnectLogAt >= TelemetryService.DISCONNECT_LOG_INTERVAL_MS) {
      this.lastCollectorDisconnectLogAt = now;
      this.logger.warn(
        `Collector disconnected (code=${code ?? 'n/a'}, reason=${reasonText}). Telemetry unavailable until it reconnects.`,
      );
    } else {
      this.logger.debug(
        `Collector disconnected (code=${code ?? 'n/a'}, reason=${reasonText}); suppressing repeated warning.`,
      );
    }
  }

  private handleCollectorMessage(data: RawMessage): void {
    const text = this.decodeMessage(data);
    if (!text) return;

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      this.logger.warn(`Failed to parse telemetry payload: ${err}; payload=${text}`);
      return;
    }

    const wrapped = Array.isArray(parsed)
      ? { metrics: parsed }
      : typeof parsed === 'object' && parsed !== null && 'metrics' in (parsed as Record<string, unknown>)
        ? (parsed as Record<string, unknown>)
        : { metrics: parsed };

    const message = JSON.stringify(wrapped);
    this.broadcastToClients(message);
  }

  private broadcastToClients(message: string): void {
    const disconnected: WebSocket[] = [];
    this.clientSockets.forEach((client) => {
      if (client.readyState !== WebSocket.OPEN) {
        disconnected.push(client);
        return;
      }

      try {
        client.send(message);
      } catch (err) {
        this.logger.warn(`Error sending telemetry to client: ${err}`);
        disconnected.push(client);
      }
    });

    if (disconnected.length > 0) {
      disconnected.forEach((client) => this.clientSockets.delete(client));
      this.logger.log(`Removed ${disconnected.length} disconnected telemetry clients.`);
    }
  }

  private handleClientConnection(socket: WebSocket): void {
    this.clientSockets.add(socket);
    this.logger.debug(`Telemetry client connected; total clients=${this.clientSockets.size}`);

    socket.on('close', () => {
      this.clientSockets.delete(socket);
    });

    socket.on('error', (err) => {
      this.logger.warn(`Telemetry client error: ${err}`);
      this.clientSockets.delete(socket);
    });

    socket.on('message', () => {
      // Ignore client messages; telemetry is server-push only.
    });
  }

  private decodeMessage(data: RawMessage): string | null {
    if (typeof data === 'string') return data;
    if (data instanceof Buffer) return data.toString('utf-8');
    if (Array.isArray(data)) {
      try {
        const buffers = data
          .map((chunk) => (chunk instanceof Buffer ? chunk : Buffer.from(chunk)))
          .filter(Boolean);
        return Buffer.concat(buffers).toString('utf-8');
      } catch (err) {
        this.logger.warn(`Failed to decode telemetry array payload: ${err}`);
        return null;
      }
    }
    if (data instanceof ArrayBuffer) return Buffer.from(data).toString('utf-8');
    return null;
  }
}