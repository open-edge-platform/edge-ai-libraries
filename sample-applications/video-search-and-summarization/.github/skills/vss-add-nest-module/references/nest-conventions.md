# VSS pipeline-manager NestJS conventions catalog

Grounding source: `/sample-applications/video-search-and-summarization/pipeline-manager`.

## Tooling and baseline

- NestJS 11 (`@nestjs/common` `^11.1.6`, `@nestjs/core` `^11.1.19`).
- TypeScript `ES2021`, CommonJS, decorators enabled, `strictNullChecks: true`, `noImplicitAny: false` (`tsconfig.json`).
- Prettier: single quotes, trailing commas, width 120 (`.prettierrc`).
- ESLint uses `typescript-eslint` recommended type-checked rules, Prettier plugin, with `no-explicit-any` off and unsafe/no-floating-promises warnings (`eslint.config.mjs`).
- Scripts: `npm run build`, `npm run lint`, `npm test`, `npm run format` (`package.json`).

## Root application wiring

Reference: `src/app.module.ts`, `src/main.ts`.

- Root imports all feature modules explicitly: `StateManagerModule`, `VideoUploadModule`, `DatastoreModule`, `LanguageModelModule`, `EvamModule`, `SocketsModule`, `AudioModule`, `SearchModule`, `SummaryModule`, etc.
- `EventEmitterModule.forRoot({ delimiter: '.', maxListeners: 5 })` is configured once in root.
- `ConfigModule.forRoot({ load: [configuration], isGlobal: true })` makes config injectable globally.
- TypeORM root uses Postgres env vars and explicit entity list: `entities: [StateEntity, VideoEntity, SearchEntity, TagEntity]`, plus `migrationsRun: true`, `synchronize: true`.
- Swagger is configured in `main.ts` with title `Pipeline Manager`, tag `pipeline`, and server prefix `/manager`.

## Folder layout and naming

References: `src/summary`, `src/search`, `src/video-upload`, `src/state-manager`.

- Feature module file: `<feature>/<feature>.module.ts`.
- Controllers: `<feature>/controllers/<feature>.controller.ts` except state-manager also has top-level `states.controller.ts` and `pipeline.controller.ts`.
- Services: `<feature>/services/<name>.service.ts`.
- DB services: `<feature>/services/<feature>-db.service.ts`.
- Queues: `state-manager/queues/<task>.service.ts`.
- DTO/interface/model files: `<feature>/models/*.model.ts` or `search/model/*.model.ts` (search uses singular `model`).
- Entities: `<feature>/models/*.entity.ts` or `search/model/search.entity.ts`.

## Module conventions

References:

- `summary/summary.module.ts` imports `VideoUploadModule`, `StateManagerModule`; provides `SummaryService`; controls `SummaryController`; exports nothing.
- `search/search.module.ts` imports `HttpModule`, `TypeOrmModule.forFeature([SearchEntity])`, `VideoUploadModule`; provides state/db/shim services.
- `video-upload/video-upload.module.ts` imports domain modules and `TypeOrmModule.forFeature([VideoEntity, TagEntity])`; exports services other modules need.
- `state-manager/state-manager.module.ts` imports many domain modules plus `TypeOrmModule.forFeature([StateEntity])`; exports `StateService`, `UiService`, `AudioQueueService`.

Convention:

```ts
@Module({
  providers: [FeatureService, FeatureDbService],
  controllers: [FeatureController],
  imports: [DependencyModule, TypeOrmModule.forFeature([FeatureEntity])],
  exports: [FeatureService],
})
export class FeatureModule {}
```

Why: provider visibility is explicit. Do not instantiate service classes manually.

## Dependency injection style

References: `summary/controllers/summary.controller.ts`, `search/services/search-state.service.ts`, `video-upload/services/video.service.ts`.

- Constructor injection is used everywhere.
- Private dependency fields often use `$` prefixes: `private $state: StateService`, `private $emitter: EventEmitter2`, `private $config: ConfigService`.
- Service classes use `@Injectable()`.
- Controllers use `@Controller(...)` and Swagger decorators.
- TypeORM repositories use `@InjectRepository(Entity)` in a DB service, not in controllers.

Examples:

```ts
constructor(
  private $searchDB: SearchDbService,
  private $video: VideoService,
  private $emitter: EventEmitter2,
) {}
```

```ts
constructor(
  @InjectRepository(VideoEntity) private videoRepo: Repository<VideoEntity>,
) {}
```

## Controller conventions

References: `summary/controllers/summary.controller.ts`, `search/controllers/search.controller.ts`, `video-upload/controllers/video.controller.ts`.

- Decorate with `@ApiTags('Feature')` and `@Controller('route')`.
- Use route methods `@Get`, `@Post`, `@Patch`, `@Delete`.
- Use `@ApiOperation`, `@ApiBody`, `@ApiParam`, `@ApiOkResponse`, `@ApiCreatedResponse`.
- Throw Nest HTTP exceptions (`BadRequestException`, `NotFoundException`, `UnprocessableEntityException`, `InternalServerErrorException`).
- Delegate business logic to injected services.

Example references:

- `SearchController.addQuery()` parses tag CSV and calls `SearchStateService.newQuery()`.
- `SummaryController.startSummaryPipeline()` validates input, retrieves video/config, creates state.
- `VideoController.videoUpload()` handles `FileInterceptor('video')`, validates streamability, and delegates upload.

## Model and Swagger DTO conventions

References: `summary/models/summary-pipeline.model.ts`, `search/model/search.model.ts`, `video-upload/models/video.swagger.ts`.

- Internal shape: `interface` or simple class.
- Swagger shape: class with `@ApiProperty` / `@ApiPropertyOptional`.
- Enums are exported from model files when persisted or used in DTOs (`SearchQueryStatus`).
- Request DTO classes end in `DTO`; response interfaces/classes may end in `RO`.

Example:

```ts
export interface SummaryPipelinRO {
  summaryPipelineId: string;
}

export class SummaryPipelineROSwagger implements SummaryPipelinRO {
  @ApiProperty({ description: 'ID of the created summary pipeline state' })
  summaryPipelineId: string;
}
```

## TypeORM entity and repository conventions

References: `video-upload/models/video.entity.ts`, `search/model/search.entity.ts`, `state-manager/models/state.entity.ts`; DB services `video-db.service.ts`, `search-db.service.ts`, `state-db.service.ts`.

- Entities use `@Entity('table_name')` with a generated `dbId` primary key and a separate unique domain ID (`videoId`, `queryId`, `stateId`).
- Timestamps are usually text ISO strings (`createdAt`, `updatedAt`) except `StateEntity` uses `@CreateDateColumn` / `@UpdateDateColumn`.
- Arrays use Postgres array columns (`@Column({ type: 'text', array: true })`).
- Complex nested state/results use `@Column('jsonb')` or nullable `jsonb`.
- DB service methods generally include `create`, `readAll`, `read`, `update`, and sometimes `remove`.
- Updates merge partials and set `updatedAt: new Date().toISOString()`.

Example references:

- `SearchDbService.create()` calls `this.searchRepo.create(...)`, applies flattened time filter fields, then `save()`.
- `VideoDbService.read(videoId)` uses `findOne({ where: { videoId } })` and returns `null` if absent.

## Event conventions

References: `events/Pipeline.events.ts`, `events/app.events.ts`, `events/socket.events.ts`; usage in `pipeline.service.ts`, `search-state.service.ts`, queue services.

- Event names are centralized in enums.
- Names are dot-delimited because root `EventEmitterModule` uses delimiter `.`.
- Pipeline events use `pipeline.*`, search events use `search.*`, app events use `app.*`, socket bridge events use `socket.*`.
- Payloads are typed interfaces in the same event file when reusable.
- Emit with injected `EventEmitter2`; listen with `@OnEvent(Enum.VALUE)`.

Examples:

```ts
export enum PipelineEvents {
  SUMMARY_PIPELINE_START = 'pipeline.summary.start',
  SUMMARY_STREAM = 'pipeline.summary.stream',
  SUMMARY_COMPLETE = 'pipeline.summary.complete',
}
```

```ts
this.$event.emit(PipelineEvents.CHUNKING_TRIGGERED, { stateId });

@OnEvent(PipelineEvents.CHUNK_RECEIVED)
async triggerChunkCaptioning(chunkData: ChunkQueue) { ... }
```

## Queue conventions

References: `state-manager/queues/chunking.service.ts`, `summary-queue.service.ts`, `audio-queue.service.ts`, `app.service.ts`.

- `AppService` emits `AppEvents.TICK` and `AppEvents.FAST_TICK` from `setInterval`; intervals are read from config keys `tick.interval` and `tick.fastInterval`.
- Queue services are providers, not controllers.
- In-memory queue fields are public-ish class members such as `waiting: SummaryQueueItem[] = []`, `processing: SummaryQueueItem[] = []`, or `audioProcessing: Set<string>`.
- Enqueue on domain events (`PipelineEvents.SUMMARY_TRIGGER`, `PipelineEvents.AUDIO_TRIGGERED`).
- Process on `@OnEvent(AppEvents.FAST_TICK)` when capacity exists.
- Guard duplicate queue entries by checking waiting/processing and state status.
- Emit progress/completion events; separate handlers remove processing entries and decrement counters.
- Clean stale entries on `AppEvents.SUMMARY_REMOVED`.

Example references:

- `SummaryQueueService.processQueue()` finds a ready item, moves it from waiting to processing, then starts video/audio summary.
- `ChunkingService.checkProcessing()` checks VLM slots and service readiness before dispatch.
- `AudioQueueService.startAudioProcessing()` adds state to `audioProcessing`, calls audio service, removes on success/error, emits follow-up events.

## WebSocket gateway conventions

References: `sockets/sockets.module.ts`, `sockets/events.gateway.ts`, `events/socket.events.ts`.

- One gateway class `EventsGateway` with `@WebSocketGateway({ cors: { origin: '*' }, path: '/ws/' })`.
- `SocketsModule` provides/exports the gateway and imports `StateManagerModule` for `UiService`.
- Gateway listens to internal events with `@OnEvent(SocketEvent.X)` and emits Socket.IO names.
- State-specific clients join a room through `@SubscribeMessage('join')`; server emits to `this.server.to(stateId)`.
- Search uses global socket events: `search:sync`, `search:update`.
- Summary state uses names like `summary:sync/${stateId}/status`, `summary:sync/${stateId}/summaryStream`.

## Config conventions

References: `config/configuration.ts`, `search/services/search-shim.service.ts`, `datastore/services/datastore.service.ts`, `state-manager/queues/*.service.ts`.

- All app config lives in `configuration.ts` as nested objects loaded globally.
- Env vars are read and normalized there where possible.
- Services inject `ConfigService` and access dot paths.
- Non-null assertions (`!`) are common for required config.

Examples:

```ts
const endPoint: string = this.$config.get('search.endpoint')!;
const bucket = this.$config.get<string>('datastore.bucketName')!;
const maxConcurrent = this.$config.get<number>('openai.vlmCaptioning.concurrent')!;
```

## External HTTP/shim conventions

References: `search/services/search-shim.service.ts`, `datastore/datastore.module.ts`, `data-prep` services.

- Use `HttpModule` or `HttpModule.registerAsync(...)` in the module.
- Inject `HttpService` into shim services.
- Convert Observables in callers using `lastValueFrom(...)` when an `async` method needs the result.
- Keep endpoint construction in shim/service classes, not controllers.

## Registration checklist for a new feature

1. Add `src/<feature>/<feature>.module.ts` with providers/controllers/imports/exports.
2. Add models/DTOs; add entity + DB service only when persisted.
3. If entity exists, add `TypeOrmModule.forFeature([Entity])` in the feature module.
4. If entity exists, import it in `src/app.module.ts` and add it to root `entities: [...]`.
5. If adding events, extend the proper enum under `src/events/` and use typed payloads.
6. If adding queued work, add queue provider and wire `@OnEvent(AppEvents.FAST_TICK)` processing.
7. If adding websocket output, add a `SocketEvent` enum value and a handler in `sockets/events.gateway.ts`.
8. If other modules need your service, export it and import your module where needed.
9. If adding env/config, update `src/config/configuration.ts` and use `ConfigService` dot paths.
10. Register the feature module in root `AppModule.imports`.
11. Run existing checks from `pipeline-manager`: `npm run build`, relevant `npm test`, `npm run lint`.
