import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowDownToLine,
  CheckCircle2,
  Clock3,
  CloudUpload,
  ExternalLink,
  FileSearch,
  HardDriveDownload,
  Link2,
  ListRestart,
  LoaderCircle,
  MonitorDot,
  Music2,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import type {
  MediaJob,
  MediaJobStatus,
  MediaQuality,
  MediaWorkflow,
  WorkerStatusResponse,
} from '@shared/api.interface';

import {
  createMediaJob,
  getApiErrorMessage,
  getWorkerStatus,
  listMediaJobs,
  retryMediaJob,
} from '@/api/jobs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';

const ACTIVE_STATUSES: MediaJobStatus[] = [
  'queued',
  'claimed',
  'inspecting',
  'downloading',
  'uploading',
];

const STATUS_COPY: Record<MediaJobStatus, string> = {
  queued: '等待本机',
  claimed: '已领取',
  inspecting: '解析中',
  downloading: '下载中',
  uploading: '上传中',
  completed: '已完成',
  failed: '失败',
};

const WORKFLOW_COPY: Record<MediaWorkflow, string> = {
  video: '内容下载',
  audio: '音频 MP3',
  inspect: '只解析',
};

const PLATFORM_COPY: Record<MediaJob['platform'], string> = {
  youtube: 'YouTube',
  bilibili: 'Bilibili',
  xiaohongshu: '小红书',
  x: 'X',
  threads: 'Threads',
};

const DATE_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

interface WorkflowOption {
  value: MediaWorkflow;
  label: string;
  detail: string;
  icon: React.ComponentType<{ className?: string }>;
}

const WORKFLOW_OPTIONS: WorkflowOption[] = [
  {
    value: 'video',
    label: '下载内容',
    detail: '视频 / 图文 / 文字',
    icon: ArrowDownToLine,
  },
  {
    value: 'audio',
    label: '提取音频',
    detail: '输出 MP3',
    icon: Music2,
  },
  {
    value: 'inspect',
    label: '只看信息',
    detail: '不下载文件',
    icon: FileSearch,
  },
];

const QUALITY_OPTIONS: MediaQuality[] = ['1080', 'best', '720', '480'];

const detectPlatform = (value: string): string => {
  const normalized: string = value.toLowerCase();
  if (
    normalized.includes('threads.com') ||
    normalized.includes('threads.net')
  ) {
    return 'Threads';
  }
  if (normalized.includes('youtube.com') || normalized.includes('youtu.be')) {
    return 'YouTube';
  }
  if (normalized.includes('bilibili.com') || normalized.includes('b23.tv')) {
    return 'Bilibili';
  }
  if (
    normalized.includes('xiaohongshu.com') ||
    normalized.includes('xhslink.com')
  ) {
    return '小红书';
  }
  if (normalized.includes('x.com') || normalized.includes('twitter.com')) {
    return 'X';
  }
  return value.trim() ? '待识别' : '自动识别平台';
};

const formatDuration = (seconds?: number): string | null => {
  if (seconds === undefined) return null;
  const minutes: number = Math.floor(seconds / 60);
  const remainder: number = seconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
};

const statusIcon = (status: MediaJobStatus): React.ReactNode => {
  const className = 'size-4';
  if (status === 'completed') return <CheckCircle2 className={className} />;
  if (status === 'failed') return <XCircle className={className} />;
  if (status === 'uploading') return <CloudUpload className={className} />;
  if (ACTIVE_STATUSES.includes(status)) {
    return <LoaderCircle className={`${className} animate-spin`} />;
  }
  return <Clock3 className={className} />;
};

const statusClassName = (status: MediaJobStatus): string => {
  if (status === 'completed') {
    return 'border-success/25 bg-success/10 text-success';
  }
  if (status === 'failed') {
    return 'border-destructive/25 bg-destructive/10 text-destructive';
  }
  if (status === 'queued') {
    return 'border-border bg-secondary text-secondary-foreground';
  }
  return 'border-primary/25 bg-primary/10 text-primary';
};

interface JobRowProps {
  job: MediaJob;
  retryingId: string | null;
  onRetry: (id: string) => Promise<void>;
}

const JobRow: React.FC<JobRowProps> = ({ job, retryingId, onRetry }) => {
  const deliveryReady = Boolean(job.deliveryUrl && (!job.deliveryExpiresAt || Date.parse(job.deliveryExpiresAt) > Date.now()));
  const duration: string | null = formatDuration(job.durationSeconds);
  const metadata: string[] = [
    PLATFORM_COPY[job.platform],
    WORKFLOW_COPY[job.workflow],
    job.workflow === 'video' && job.platform !== 'threads'
      ? `${job.quality}p`.replace('bestp', '最高画质')
      : '',
    duration ?? '',
    job.width && job.height ? `${job.width}×${job.height}` : '',
  ].filter((value: string) => Boolean(value));
  const isActive: boolean = ACTIVE_STATUSES.includes(job.status);

  return (
    <article className="group grid gap-4 border-b border-border py-5 last:border-b-0 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
      <div className="min-w-0">
        <div className="mb-2 flex flex-wrap items-start gap-2">
          <Badge
            variant="outline"
            className={`${statusClassName(job.status)} gap-1.5 tracking-wide`}
          >
            {statusIcon(job.status)}
            {job.status === 'completed' && job.workflow !== 'inspect' ? '已保存到电脑' : STATUS_COPY[job.status]}
          </Badge>
          <span className="font-mono text-xs tracking-wide text-muted-foreground">
            {DATE_FORMATTER.format(new Date(job.createdAt))}
          </span>
        </div>
        <h3 className="truncate text-base font-semibold tracking-tight text-foreground">
          {job.title || new URL(job.sourceUrl).hostname}
        </h3>
        <a
          className="mt-1 block truncate font-mono text-xs tracking-wide text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          href={job.sourceUrl}
          target="_blank"
          rel="noreferrer"
        >
          {job.sourceUrl}
        </a>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs tracking-wide text-muted-foreground">
          {metadata.map((item: string) => (
            <span key={item}>{item}</span>
          ))}
          {job.uploader ? <span>来自 {job.uploader}</span> : null}
        </div>
        {isActive ? (
          <div
            className="mt-4 max-w-xl"
            aria-label={`任务进度 ${job.progress}%`}
          >
            <div className="mb-1.5 flex items-center justify-between font-mono text-[11px] tracking-wider text-muted-foreground">
              <span>{STATUS_COPY[job.status]}</span>
              <span className="tabular-nums">{job.progress}%</span>
            </div>
            <Progress
              value={job.progress}
              className="h-1.5 rounded-sm bg-primary/10"
            />
          </div>
        ) : null}
        {job.errorMessage ? (
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-destructive">
            {job.errorMessage}
          </p>
        ) : null}
        {job.outputName ? (
          <p className="mt-3 truncate font-mono text-xs tracking-wide text-foreground">
            {job.outputName}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2 md:justify-end">
        {deliveryReady ? (
          <Button asChild size="sm" data-ai-section-type="button">
            <a href={job.deliveryUrl} target="_blank" rel="noreferrer">
              <HardDriveDownload aria-hidden="true" />
              下载到当前设备
            </a>
          </Button>
        ) : job.deliveryUrl ? <span className="text-xs text-muted-foreground">下载链接已过期，原文件仍在电脑</span> : null}
        {job.status === 'failed' ? (
          <Button
            size="sm"
            variant="outline"
            disabled={retryingId === job.id}
            onClick={() => void onRetry(job.id)}
            data-ai-section-type="button"
          >
            <ListRestart aria-hidden="true" />
            {retryingId === job.id ? '排队中…' : '重新排队'}
          </Button>
        ) : null}
        <Button asChild size="sm" variant="ghost" data-ai-section-type="button">
          <a href={job.sourceUrl} target="_blank" rel="noreferrer">
            <ExternalLink aria-hidden="true" />
            原链接
          </a>
        </Button>
      </div>
    </article>
  );
};

const JobsPage: React.FC = () => {
  const [sourceUrl, setSourceUrl] = useState<string>('');
  const [workflow, setWorkflow] = useState<MediaWorkflow>('video');
  const [quality, setQuality] = useState<MediaQuality>('1080');
  const [jobs, setJobs] = useState<MediaJob[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workerStatus, setWorkerStatus] = useState<WorkerStatusResponse | null>(
    null,
  );

  const platformHint: string = useMemo(
    () => detectPlatform(sourceUrl),
    [sourceUrl],
  );
  const hasActiveJobs: boolean = jobs.some((job: MediaJob) =>
    ACTIVE_STATUSES.includes(job.status),
  );

  const refreshJobs = useCallback(
    async (showLoading: boolean = false): Promise<void> => {
      if (showLoading) setLoading(true);
      try {
        const [jobsResponse, workerResponse] = await Promise.all([
          listMediaJobs(40),
          getWorkerStatus(),
        ]);
        setJobs(jobsResponse.items);
        setWorkerStatus(workerResponse);
        setError(null);
      } catch (requestError: unknown) {
        setError(getApiErrorMessage(requestError));
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void refreshJobs(true);
  }, [refreshJobs]);

  useEffect(() => {
    const intervalMs: number = hasActiveJobs ? 4000 : 12000;
    const timer: ReturnType<typeof setInterval> = setInterval(() => {
      void refreshJobs(false);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [hasActiveJobs, refreshJobs]);

  const handleSubmit = async (): Promise<void> => {
    const normalizedUrl: string = sourceUrl.trim();
    if (!normalizedUrl) {
      setError('请先粘贴媒体链接');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createMediaJob({ sourceUrl: normalizedUrl, workflow, quality });
      setSourceUrl('');
      toast.success(
        workflow === 'inspect' ? '解析任务已加入队列' : '下载任务已加入队列',
      );
      await refreshJobs(false);
    } catch (requestError: unknown) {
      setError(getApiErrorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = async (id: string): Promise<void> => {
    setRetryingId(id);
    try {
      await retryMediaJob(id);
      toast.success('任务已重新排队');
      await refreshJobs(false);
    } catch (requestError: unknown) {
      toast.error(getApiErrorMessage(requestError));
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <main className="workbench-grid min-h-screen bg-background text-foreground">
      <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-5 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-md bg-foreground text-background shadow-sm">
              <ArrowDownToLine className="size-5" aria-hidden="true" />
            </div>
            <div>
              <p className="font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-primary">
                Media / DL
              </p>
              <h1 className="text-lg font-semibold tracking-tight">
                媒体下载工作台
              </h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs tracking-wide text-muted-foreground">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5">
              <MonitorDot
                className={`size-3.5 ${
                  workerStatus?.online
                    ? 'text-success'
                    : 'text-muted-foreground'
                }`}
                aria-hidden="true"
              />
              {workerStatus === null
                ? '正在检测 Worker'
                : workerStatus.online
                  ? '本机 Worker 在线'
                  : '本机 Worker 离线'}
            </span>
            <span className="rounded-md border border-border bg-background px-2.5 py-1.5">
              默认保存到电脑 Downloads
            </span>
          </div>
        </header>

        <section className="py-10 sm:py-14" aria-labelledby="download-heading">
          <div className="mb-7 max-w-2xl">
            <p className="mb-2 font-mono text-xs font-medium uppercase tracking-[0.14em] text-primary">
              固定工作流 · 无需对话
            </p>
            <h2
              id="download-heading"
              className="text-balance text-3xl font-semibold leading-tight tracking-[-0.025em] sm:text-4xl"
            >
              粘贴链接，文件在本机完成下载。
            </h2>
            <p className="mt-3 max-w-xl text-pretty text-base leading-relaxed text-muted-foreground">
              支持 YouTube、Bilibili、小红书、X 和 Threads。 Threads
              可保存文字、图片、视频和动图，文件直接进入电脑的 Downloads。
            </p>
          </div>

          <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
            <div className="border-b border-border p-4 sm:p-6">
              <label
                htmlFor="source-url"
                className="mb-2 block text-sm font-medium tracking-wide"
              >
                媒体链接
              </label>
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
                <div className="relative min-w-0">
                  <Link2
                    className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <Input
                    id="source-url"
                    type="url"
                    inputMode="url"
                    autoComplete="off"
                    spellCheck={false}
                    value={sourceUrl}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                      setSourceUrl(event.target.value)
                    }
                    onKeyDown={(
                      event: React.KeyboardEvent<HTMLInputElement>,
                    ) => {
                      if (event.key === 'Enter' && !submitting)
                        void handleSubmit();
                    }}
                    placeholder="https://x.com/..."
                    aria-describedby="platform-hint"
                    aria-invalid={Boolean(error)}
                    className="h-12 rounded-md bg-background pl-10 pr-28 font-mono text-sm shadow-none"
                  />
                  <span
                    id="platform-hint"
                    className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[11px] tracking-wide text-muted-foreground"
                  >
                    {platformHint}
                  </span>
                </div>
                <Button
                  size="lg"
                  disabled={submitting}
                  onClick={() => void handleSubmit()}
                  className="min-w-36 tracking-wide"
                  data-ai-section-type="button"
                >
                  {submitting ? (
                    <LoaderCircle className="animate-spin" aria-hidden="true" />
                  ) : (
                    <ArrowDownToLine aria-hidden="true" />
                  )}
                  {submitting
                    ? '正在排队…'
                    : workflow === 'inspect'
                      ? '开始解析'
                      : '加入下载队列'}
                </Button>
              </div>
            </div>

            <div className="grid gap-6 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                  选择工作流
                </p>
                <div
                  className="grid gap-2 sm:grid-cols-3"
                  role="group"
                  aria-label="工作流"
                >
                  {WORKFLOW_OPTIONS.map((option: WorkflowOption) => {
                    const Icon = option.icon;
                    const selected: boolean = workflow === option.value;
                    return (
                      <Button
                        key={option.value}
                        type="button"
                        variant={selected ? 'secondary' : 'outline'}
                        aria-pressed={selected}
                        onClick={() => setWorkflow(option.value)}
                        className={`h-auto justify-start px-3 py-3 text-left ${
                          selected
                            ? 'border-primary/30 bg-primary/10 text-foreground'
                            : ''
                        }`}
                        data-ai-section-type="button"
                      >
                        <Icon
                          className={selected ? 'text-primary' : ''}
                          aria-hidden="true"
                        />
                        <span>
                          <span className="block text-sm font-semibold">
                            {option.label}
                          </span>
                          <span className="block text-xs font-normal text-muted-foreground">
                            {option.detail}
                          </span>
                        </span>
                      </Button>
                    );
                  })}
                </div>
              </div>

              <div className={workflow === 'video' ? '' : 'opacity-45'}>
                <p className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                  视频画质
                </p>
                <div
                  className="flex flex-wrap gap-1.5"
                  role="group"
                  aria-label="视频画质"
                >
                  {QUALITY_OPTIONS.map((option: MediaQuality) => (
                    <Button
                      key={option}
                      type="button"
                      size="sm"
                      variant={quality === option ? 'secondary' : 'ghost'}
                      disabled={workflow !== 'video'}
                      aria-pressed={quality === option}
                      onClick={() => setQuality(option)}
                      className="font-mono tracking-wide"
                      data-ai-section-type="button"
                    >
                      {option === 'best' ? '最高' : `${option}p`}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {error ? (
            <Alert variant="destructive" className="mt-4 bg-destructive/5">
              <AlertCircle aria-hidden="true" />
              <AlertTitle>任务没有提交</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {workerStatus !== null && !workerStatus.online ? (
            <Alert className="mt-4 bg-muted/40">
              <MonitorDot aria-hidden="true" />
              <AlertTitle>本机 Worker 目前离线</AlertTitle>
              <AlertDescription>
                提交后任务会保留在队列中，启动本机 Worker 后会自动继续。
              </AlertDescription>
            </Alert>
          ) : null}

          <ol
            className="mt-6 grid grid-cols-4 border-y border-border bg-background/80"
            aria-label="处理流程"
          >
            {['提交链接', '电脑领取', '解析下载', '保存 Downloads'].map(
              (label: string, index: number) => (
                <li
                  key={label}
                  className="relative border-r border-border px-2 py-3 text-center last:border-r-0 sm:px-4"
                >
                  <span className="block font-mono text-[10px] font-medium tracking-widest text-primary">
                    0{index + 1}
                  </span>
                  <span className="mt-1 block text-xs font-medium tracking-wide sm:text-sm">
                    {label}
                  </span>
                </li>
              ),
            )}
          </ol>
        </section>

        <section aria-labelledby="history-heading">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-foreground pb-3">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                Recent jobs / {String(jobs.length).padStart(2, '0')}
              </p>
              <h2
                id="history-heading"
                className="mt-1 text-xl font-semibold tracking-tight"
              >
                最近任务
              </h2>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void refreshJobs(true)}
              disabled={loading}
              data-ai-section-type="button"
            >
              <RefreshCw
                className={loading ? 'animate-spin' : ''}
                aria-hidden="true"
              />
              刷新
            </Button>
          </div>

          <div role="status" aria-live="polite">
            {loading ? (
              <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
                <LoaderCircle
                  className="size-4 animate-spin"
                  aria-hidden="true"
                />
                正在读取任务…
              </div>
            ) : jobs.length === 0 ? (
              <Empty className="min-h-56 border-0">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <ArrowDownToLine aria-hidden="true" />
                  </EmptyMedia>
                  <EmptyTitle>还没有下载任务</EmptyTitle>
                  <EmptyDescription>
                    粘贴第一个链接，查看进度；下载完成后到电脑的 Downloads 取文件。
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div data-ai-section-type="card-list">
                {jobs.map((job: MediaJob) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    retryingId={retryingId}
                    onRetry={handleRetry}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
};

export default JobsPage;
