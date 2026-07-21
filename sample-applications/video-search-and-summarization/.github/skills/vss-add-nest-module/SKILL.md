---
name: vss-add-nest-module
description: Scaffolds and wires a new NestJS service/module for the Video Search & Summarization sample app's pipeline-manager using the repo's real conventions. Use when asked to add a new service/module to pipeline-manager, extend the VSS orchestrator, add a new endpoint/queue/event to pipeline-manager, or scaffold a NestJS module the repo way for the video-search-and-summarization sample app.
---

# Add a VSS pipeline-manager NestJS module

Use this when adding a new `pipeline-manager/src/<feature>/` capability. First read nearby modules again (`summary`, `search`, `video-upload`, `state-manager`) because this repo has concrete patterns that matter more than generic NestJS advice.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-add-nest-module. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-add-nest-module"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## 1. Match the repo layout

Most feature modules use this shape:

```text
src/<feature>/
  <feature>.module.ts
  controllers/<feature>.controller.ts
  services/<feature>.service.ts
  services/<feature>-db.service.ts        # only when TypeORM-backed
  queues/<feature>-queue.service.ts       # only when tick/event queued
  models/<feature>.model.ts
  models/<feature>.entity.ts              # only when persisted
```

Why: controllers stay thin, services hold orchestration, `*-db.service.ts` isolates TypeORM repository access, queues are event-driven processors, and `models/` keeps DTO/interfaces/entities close to the feature.

Real examples:

```ts
// summary/summary.module.ts
@Module({
  imports: [VideoUploadModule, StateManagerModule],
  controllers: [SummaryController],
  providers: [SummaryService],
})
export class SummaryModule {}
```

```ts
// search/search.module.ts
@Module({
  providers: [SearchStateService, SearchDbService, SearchShimService],
  controllers: [SearchController],
  imports: [HttpModule, TypeOrmModule.forFeature([SearchEntity]), VideoUploadModule],
  exports: [],
})
export class SearchModule {}
```

## 2. Create model/DTO files first

Use interfaces for internal shapes and Swagger classes for request/response documentation, as in `summary/models/summary-pipeline.model.ts` and `search/model/search.model.ts`.

```ts
export class SearchQueryDTO {
  @ApiProperty({ description: 'Search query string', example: 'person walking' })
  query: string;

  @ApiPropertyOptional({ description: 'Comma-separated tags to filter by' })
  tags?: string;
}
```

Why: controllers can type request bodies while Swagger gets concrete classes with decorators.

## 3. Add TypeORM only if the feature persists data

Entity pattern:

```ts
@Entity('search')
export class SearchEntity {
  @PrimaryGeneratedColumn()
  dbId?: number;

  @Column({ unique: true })
  queryId: string;

  @Column('jsonb', { nullable: true })
  results: SearchResult[];
}
```

Repository pattern:

```ts
@Injectable()
export class SearchDbService {
  constructor(
    @InjectRepository(SearchEntity)
    private searchRepo: Repository<SearchEntity>,
  ) {}

  async read(queryId: string): Promise<SearchEntity | null> {
    const search = await this.searchRepo.findOne({ where: { queryId } });
    return search ?? null;
  }
}
```

Wire the entity in two places:

1. Feature module: `TypeOrmModule.forFeature([NewEntity])`.
2. Root `app.module.ts`: add `NewEntity` to `TypeOrmModule.forRoot({ entities: [...] })`.

Why: `forFeature` enables repository injection in the feature; the root entity list lets TypeORM create/sync the table.

## 4. Keep controllers thin and Swagger-tagged

Controllers inject services using the repo's `$name` property style and expose REST routes with `@ApiTags`, `@ApiOperation`, `@ApiBody`, `@ApiParam`, and response decorators.

```ts
@ApiTags('Search')
@Controller('search')
export class SearchController {
  constructor(private $search: SearchStateService) {}

  @Post('')
  @ApiOperation({ summary: 'Add a new search query' })
  @ApiBody({ type: SearchQueryDTO })
  async addQuery(@Body() reqBody: SearchQueryDTO) {
    return await this.$search.newQuery(reqBody.query);
  }
}
```

Why: validation/errors and orchestration live in services; controllers translate HTTP to typed service calls.

## 5. Use DI through modules, not ad hoc construction

Import modules that export the services you need. Examples:

- `SummaryModule` imports `VideoUploadModule` and `StateManagerModule` to inject `VideoService`, `AppConfigService`, `StateService`, `UiService`.
- `VideoUploadModule` exports `AppConfigService`, `FeaturesService`, `VideoService`, `VideoDbService`.
- `StateManagerModule` exports `StateService`, `UiService`, `AudioQueueService`.

If another module must inject your service, add it to `exports`.

Why: Nest resolves providers only across module boundaries through `imports`/`exports`.

## 6. Add events using the central enums

Define new event names in `src/events/Pipeline.events.ts`, `src/events/app.events.ts`, or `src/events/socket.events.ts`. Use dot-delimited names because root wiring uses:

```ts
EventEmitterModule.forRoot({ delimiter: '.', maxListeners: 5 })
```

Emit and listen like existing services:

```ts
this.$emitter.emit(SearchEvents.RUN_QUERY, res.queryId);

@OnEvent(SearchEvents.RUN_QUERY)
async reRunQuery(queryId: string) { ... }
```

Pipeline examples include `pipeline.summary.start`, `pipeline.chunking.complete`, and `pipeline.summary.stream`. App tick events are emitted by `AppService` and consumed by queues.

Why: event enums prevent string drift and decouple controllers/services/queues/gateways.

## 7. Use the repo queue pattern for background work

Queue processors are injectable services under `state-manager/queues` or a feature `queues/` folder. They keep in-memory `waiting`/`processing` state, enqueue on a domain event, process on `AppEvents.FAST_TICK`, emit progress/completion events, and remove stale work on `AppEvents.SUMMARY_REMOVED`.

```ts
@Injectable()
export class SummaryQueueService {
  waiting: SummaryQueueItem[] = [];
  processing: SummaryQueueItem[] = [];

  @OnEvent(PipelineEvents.SUMMARY_TRIGGER)
  streamTrigger({ stateId }: PipelineDTOBase) {
    this.waiting.push({ stateId, taskType: 'videoSummary' });
  }

  @OnEvent(AppEvents.FAST_TICK)
  processQueue() {
    if (this.waiting.length > 0 && this.$inferenceCount.hasLlmSlots()) {
      const queueItem = this.waiting.shift()!;
      this.processing.push(queueItem);
      this.startVideoSummary(queueItem);
    }
  }
}
```

Why: long-running work is throttled centrally and does not block HTTP requests.

## 8. Send UI updates through SocketEvent + EventsGateway

Add socket event enum values to `src/events/socket.events.ts`, emit them from state/services, and add `@OnEvent(...)` handlers in `sockets/events.gateway.ts`.

```ts
@OnEvent(SocketEvent.SEARCH_UPDATE)
searchUpdate(payload: SearchQuery) {
  this.server.emit('search:update', payload);
}
```

For state-specific updates, join clients to a state room and emit names like `summary:sync/${stateId}/status`.

Why: services remain transport-agnostic; only the gateway knows Socket.IO event names and rooms.

## 9. Read configuration through ConfigService

Add config keys in `src/config/configuration.ts`, then inject `ConfigService`:

```ts
constructor(private $config: ConfigService) {}

const endPoint: string = this.$config.get('search.endpoint')!;
const maxConcurrent = this.$config.get<number>('openai.vlmCaptioning.concurrent')!;
```

Why: this app centralizes environment parsing and nested config names (`search.endpoint`, `datastore.bucketName`, `tick.fastInterval`).

## 10. Register the module in root wiring

In `src/app.module.ts`:

```ts
import { NewFeatureModule } from './new-feature/new-feature.module';
import { NewFeatureEntity } from './new-feature/models/new-feature.entity';

@Module({
  imports: [
    // existing imports...
    TypeOrmModule.forRoot({
      // existing options...
      entities: [StateEntity, VideoEntity, SearchEntity, TagEntity, NewFeatureEntity],
    }),
    NewFeatureModule,
  ],
})
export class AppModule {}
```

Place `EventEmitterModule.forRoot(...)` once only; do not add another root event emitter.

## 11. Validate

From `pipeline-manager/`, run existing checks only:

```bash
npm run build
npm test -- --runInBand
npm run lint
```

If changing only docs or templates, no app build is required. If adding entities, verify migrations/sync behavior is acceptable for this sample (`synchronize: true`, `migrationsRun: true` are already set).

See [references/nest-conventions.md](references/nest-conventions.md) for a catalog of actual repo conventions and file references. Use [assets/module-template/](assets/module-template/) as a starting scaffold, then rename `example` to the real feature.
