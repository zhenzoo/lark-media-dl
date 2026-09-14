import {
  BadRequestException,
  Inject,
  Injectable,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import {
  DRIZZLE_DATABASE,
  type PostgresJsDatabase,
} from '@lark-apaas/fullstack-nestjs-core';
import { and, asc, desc, eq, inArray, lt } from 'drizzle-orm';

import { mediaJob, mediaWorkerRuntime } from '@server/database/schema';
import type {
  ClaimMediaJobResponse,
  CreateMediaJobRequest,
  ListMediaJobsResponse,
  MediaJob,
  MediaJobResponse,
  MediaJobStatus,
  MediaPlatform,
  UpdateMediaJobRequest,
  UpdateMediaJobResponse,
  WorkerHeartbeatRequest,
  WorkerHeartbeatResponse,
  WorkerProgressStatus,
  WorkerStatusResponse,
} from '@shared/api.interface';
import { validateCompletion } from './completion';

type MediaJobRow = typeof mediaJob.$inferSelect;
type MediaJobInsert = typeof mediaJob.$inferInsert;
type MediaWorkerRuntimeRow = typeof mediaWorkerRuntime.$inferSelect;

const ACTIVE_STATUSES: MediaJobStatus[] = [
  'claimed',
  'inspecting',
  'downloading',
  'uploading',
];
const STALE_AFTER_MS = 15 * 60 * 1000;
const POLL_AFTER_SECONDS = 4;
const WORKER_ONLINE_AFTER_MS = 30 * 1000;

const TRANSITIONS: Record<MediaJobStatus, readonly WorkerProgressStatus[]> = {
  queued: [],
  claimed: ['inspecting', 'downloading', 'uploading', 'completed', 'failed'],
  inspecting: ['inspecting', 'downloading', 'uploading', 'completed', 'failed'],
  downloading: ['downloading', 'uploading', 'completed', 'failed'],
  uploading: ['uploading', 'completed', 'failed'],
  completed: [],
  failed: [],
};

@Injectable()
class JobsService {
  private readonly logger = new Logger(JobsService.name);

  constructor(
    @Inject(DRIZZLE_DATABASE)
    private readonly db: PostgresJsDatabase,
  ) {}

  async list(limit: number): Promise<ListMediaJobsResponse> {
    const rows: MediaJobRow[] = await this.db
      .select()
      .from(mediaJob)
      .orderBy(desc(mediaJob.createdAt))
      .limit(limit);
    return { items: rows.map((row: MediaJobRow) => this.toMediaJob(row)) };
  }

  async getWorkerStatus(): Promise<WorkerStatusResponse> {
    const rows: MediaWorkerRuntimeRow[] = await this.db
      .select()
      .from(mediaWorkerRuntime)
      .orderBy(desc(mediaWorkerRuntime.lastSeen))
      .limit(1);
    const worker: MediaWorkerRuntimeRow | undefined = rows[0];
    if (!worker) return { online: false };
    return {
      online: Date.now() - worker.lastSeen.getTime() <= WORKER_ONLINE_AFTER_MS,
      workerId: worker.id,
      version: worker.version,
      lastSeen: worker.lastSeen.toISOString(),
    };
  }

  async heartbeat(
    input: WorkerHeartbeatRequest,
  ): Promise<WorkerHeartbeatResponse> {
    const workerId: string = this.normalizeWorkerId(input.workerId);
    const version: string = input.version.trim();
    const now: Date = new Date();
    const rows: MediaWorkerRuntimeRow[] = await this.db
      .insert(mediaWorkerRuntime)
      .values({ id: workerId, version, lastSeen: now, updatedAt: now })
      .onConflictDoUpdate({
        target: mediaWorkerRuntime.id,
        set: { version, lastSeen: now, updatedAt: now },
      })
      .returning();
    const worker: MediaWorkerRuntimeRow | undefined = rows[0];
    if (!worker) {
      throw new BadRequestException('Worker 心跳保存失败，请重试');
    }
    return {
      accepted: true,
      worker: {
        online: true,
        workerId: worker.id,
        version: worker.version,
        lastSeen: worker.lastSeen.toISOString(),
      },
    };
  }

  async create(input: CreateMediaJobRequest): Promise<MediaJobResponse> {
    const sourceUrl: string = input.sourceUrl.trim();
    const platform: MediaPlatform = this.detectPlatform(sourceUrl);
    const created: MediaJobRow[] = await this.db
      .insert(mediaJob)
      .values({
        sourceUrl,
        platform,
        workflow: input.workflow,
        quality: input.quality,
      })
      .returning();
    const row: MediaJobRow | undefined = created[0];
    if (!row) {
      throw new BadRequestException('任务创建失败，请重试');
    }
    return { job: this.toMediaJob(row) };
  }

  async retry(id: string): Promise<MediaJobResponse> {
    const row: MediaJobRow = await this.getRow(id);
    if (row.status !== 'failed') {
      throw new BadRequestException('只有失败任务可以重新排队');
    }
    const updated: MediaJobRow[] = await this.db
      .update(mediaJob)
      .set({
        status: 'queued',
        progress: 0,
        outputName: null,
        deliveryUrl: null,
        deliveryExpiresAt: null,
        errorMessage: null,
        workerId: null,
        claimedAt: null,
        completedAt: null,
        updatedAt: new Date(),
      })
      .where(eq(mediaJob.id, id))
      .returning();
    const result: MediaJobRow | undefined = updated[0];
    if (!result) {
      throw new NotFoundException('任务不存在');
    }
    return { job: this.toMediaJob(result) };
  }

  async claimNext(workerIdInput: string): Promise<ClaimMediaJobResponse> {
    const workerId: string = this.normalizeWorkerId(workerIdInput);
    await this.requeueStaleJobs();

    const assignedRows: MediaJobRow[] = await this.db
      .select()
      .from(mediaJob)
      .where(
        and(
          eq(mediaJob.workerId, workerId),
          inArray(mediaJob.status, ACTIVE_STATUSES),
        ),
      )
      .orderBy(asc(mediaJob.createdAt))
      .limit(1);
    const assigned: MediaJobRow | undefined = assignedRows[0];
    if (assigned) {
      return { job: this.toMediaJob(assigned), pollAfterSeconds: 0 };
    }

    const candidates: MediaJobRow[] = await this.db
      .select()
      .from(mediaJob)
      .where(eq(mediaJob.status, 'queued'))
      .orderBy(asc(mediaJob.createdAt))
      .limit(1);
    const candidate: MediaJobRow | undefined = candidates[0];
    if (!candidate) {
      return { job: null, pollAfterSeconds: POLL_AFTER_SECONDS };
    }

    const claimedAt: Date = new Date();
    const claimed: MediaJobRow[] = await this.db
      .update(mediaJob)
      .set({
        status: 'claimed',
        progress: 5,
        workerId,
        claimedAt,
        updatedAt: claimedAt,
      })
      .where(and(eq(mediaJob.id, candidate.id), eq(mediaJob.status, 'queued')))
      .returning();
    const result: MediaJobRow | undefined = claimed[0];
    return {
      job: result ? this.toMediaJob(result) : null,
      pollAfterSeconds: result ? 0 : POLL_AFTER_SECONDS,
    };
  }

  async updateFromWorker(
    input: UpdateMediaJobRequest,
  ): Promise<UpdateMediaJobResponse> {
    const id: string = input.jobId;
    const row: MediaJobRow = await this.getRow(id);
    const workerId: string = this.normalizeWorkerId(input.workerId);
    if (row.workerId !== workerId) {
      throw new BadRequestException('该任务已被其他 Worker 领取');
    }

    const currentStatus: MediaJobStatus = row.status as MediaJobStatus;
    if (!TRANSITIONS[currentStatus]?.includes(input.status)) {
      throw new BadRequestException(
        `任务状态不能从 ${currentStatus} 更新为 ${input.status}`,
      );
    }

    if (input.status === 'failed' && !input.errorMessage?.trim()) {
      throw new BadRequestException('失败任务必须提供错误原因');
    }
    if (input.status === 'completed') {
      const outputName: string | null = input.outputName ?? row.outputName;
      try { validateCompletion(row.workflow, outputName); }
      catch (error) { throw new BadRequestException((error as Error).message); }
    }

    const now: Date = new Date();
    const updates: Partial<MediaJobInsert> = {
      status: input.status,
      progress: this.resolveProgress(
        input.status,
        input.progress,
        row.progress,
      ),
      claimedAt: now,
      completedAt:
        input.status === 'completed' || input.status === 'failed' ? now : null,
      updatedAt: now,
    };
    this.assignOptionalFields(updates, input);

    const changed: MediaJobRow[] = await this.db
      .update(mediaJob)
      .set(updates)
      .where(and(eq(mediaJob.id, id), eq(mediaJob.workerId, workerId), eq(mediaJob.status, currentStatus)))
      .returning();
    const result: MediaJobRow | undefined = changed[0];
    if (!result) {
      throw new NotFoundException('任务不存在或已被重新领取');
    }
    return { accepted: true, job: this.toMediaJob(result) };
  }

  private async getRow(id: string): Promise<MediaJobRow> {
    const rows: MediaJobRow[] = await this.db
      .select()
      .from(mediaJob)
      .where(eq(mediaJob.id, id))
      .limit(1);
    const row: MediaJobRow | undefined = rows[0];
    if (!row) {
      throw new NotFoundException('任务不存在');
    }
    return row;
  }

  private async requeueStaleJobs(): Promise<void> {
    const cutoff: Date = new Date(Date.now() - STALE_AFTER_MS);
    const rows: MediaJobRow[] = await this.db
      .update(mediaJob)
      .set({
        status: 'queued',
        progress: 0,
        workerId: null,
        claimedAt: null,
        errorMessage: 'Worker 超过 15 分钟未更新，任务已自动重新排队',
        updatedAt: new Date(),
      })
      .where(
        and(
          inArray(mediaJob.status, ACTIVE_STATUSES),
          lt(mediaJob.claimedAt, cutoff),
        ),
      )
      .returning();
    if (rows.length > 0) {
      this.logger.warn(`已重新排队 ${String(rows.length)} 个超时任务`);
    }
  }

  private assignOptionalFields(
    updates: Partial<MediaJobInsert>,
    input: UpdateMediaJobRequest,
  ): void {
    if (input.title !== undefined) updates.title = input.title.trim();
    if (input.uploader !== undefined) updates.uploader = input.uploader.trim();
    if (input.durationSeconds !== undefined) {
      updates.durationSeconds = input.durationSeconds;
    }
    if (input.width !== undefined) updates.width = input.width;
    if (input.height !== undefined) updates.height = input.height;
    if (input.outputName !== undefined) {
      updates.outputName = input.outputName.trim();
    }
    if (input.deliveryUrl !== undefined) {
      updates.deliveryUrl = input.deliveryUrl.trim();
    }
    if (input.deliveryExpiresAt !== undefined) {
      updates.deliveryExpiresAt = new Date(input.deliveryExpiresAt);
    }
    if (input.errorMessage !== undefined) {
      updates.errorMessage = input.errorMessage.trim();
    }
  }

  private resolveProgress(
    status: WorkerProgressStatus,
    progress: number | undefined,
    current: number,
  ): number {
    if (status === 'completed') return 100;
    if (status === 'failed') return progress ?? current;
    const defaults: Record<
      Exclude<WorkerProgressStatus, 'completed' | 'failed'>,
      number
    > = {
      inspecting: 10,
      downloading: 35,
      uploading: 80,
    };
    return Math.max(current, progress ?? defaults[status]);
  }

  private normalizeWorkerId(value: string): string {
    const workerId: string = value.trim();
    if (!/^[a-zA-Z0-9._-]{1,128}$/u.test(workerId)) {
      throw new BadRequestException(
        'workerId 只能包含字母、数字、点、下划线和短横线',
      );
    }
    return workerId;
  }

  private detectPlatform(sourceUrl: string): MediaPlatform {
    let parsed: URL;
    try {
      parsed = new URL(sourceUrl);
    } catch {
      throw new BadRequestException('链接格式无效，请粘贴完整的 HTTPS 地址');
    }
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port) {
      throw new BadRequestException('只接受不含账号密码和自定义端口的 HTTPS 链接');
    }
    const host: string = parsed.hostname.toLowerCase();
    const matches: (domain: string) => boolean = (domain: string): boolean =>
      host === domain || host.endsWith(`.${domain}`);
    if (matches('youtube.com') || matches('youtu.be')) return 'youtube';
    if (matches('threads.com') || matches('threads.net')) return 'threads';
    if (matches('bilibili.com') || matches('b23.tv')) return 'bilibili';
    if (
      matches('xiaohongshu.com') ||
      matches('xhslink.com')
    ) {
      return 'xiaohongshu';
    }
    if (
      matches('x.com') ||
      matches('twitter.com') ||
      matches('fxtwitter.com') ||
      matches('vxtwitter.com')
    ) {
      return 'x';
    }
    throw new BadRequestException(
      '当前支持 YouTube、Bilibili、小红书、X 和 Threads',
    );
  }

  private toMediaJob(row: MediaJobRow): MediaJob {
    return {
      id: row.id,
      sourceUrl: row.sourceUrl,
      platform: row.platform as MediaPlatform,
      workflow: row.workflow as MediaJob['workflow'],
      quality: row.quality as MediaJob['quality'],
      status: row.status as MediaJobStatus,
      progress: row.progress,
      title: row.title ?? undefined,
      uploader: row.uploader ?? undefined,
      durationSeconds: row.durationSeconds ?? undefined,
      width: row.width ?? undefined,
      height: row.height ?? undefined,
      outputName: row.outputName ?? undefined,
      deliveryUrl: row.deliveryUrl ?? undefined,
      deliveryExpiresAt: row.deliveryExpiresAt?.toISOString(),
      errorMessage: row.errorMessage ?? undefined,
      workerId: row.workerId ?? undefined,
      claimedAt: row.claimedAt?.toISOString(),
      completedAt: row.completedAt?.toISOString(),
      createdAt: row.createdAt.toISOString(),
      updatedAt: row.updatedAt.toISOString(),
    };
  }
}

export { JobsService };
