export type MediaPlatform =
  | 'youtube'
  | 'bilibili'
  | 'xiaohongshu'
  | 'x'
  | 'threads';

export type MediaWorkflow = 'video' | 'audio' | 'inspect';

export type MediaQuality = 'best' | '1080' | '720' | '480';

export type MediaJobStatus =
  | 'queued'
  | 'claimed'
  | 'inspecting'
  | 'downloading'
  | 'uploading'
  | 'completed'
  | 'failed';

export type WorkerProgressStatus = Exclude<
  MediaJobStatus,
  'queued' | 'claimed'
>;

export interface MediaJob {
  id: string;
  sourceUrl: string;
  platform: MediaPlatform;
  workflow: MediaWorkflow;
  quality: MediaQuality;
  status: MediaJobStatus;
  progress: number;
  title?: string;
  uploader?: string;
  durationSeconds?: number;
  width?: number;
  height?: number;
  outputName?: string;
  deliveryUrl?: string;
  deliveryExpiresAt?: string;
  errorMessage?: string;
  workerId?: string;
  claimedAt?: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateMediaJobRequest {
  sourceUrl: string;
  workflow: MediaWorkflow;
  quality: MediaQuality;
}

export interface MediaJobResponse {
  job: MediaJob;
}

export interface ListMediaJobsResponse {
  items: MediaJob[];
}

export interface ClaimMediaJobResponse {
  job: MediaJob | null;
  pollAfterSeconds: number;
}

export interface UpdateMediaJobRequest {
  jobId: string;
  workerId: string;
  status: WorkerProgressStatus;
  progress?: number;
  title?: string;
  uploader?: string;
  durationSeconds?: number;
  width?: number;
  height?: number;
  outputName?: string;
  deliveryUrl?: string;
  deliveryExpiresAt?: string;
  errorMessage?: string;
}

export interface UpdateMediaJobResponse {
  accepted: true;
  job: MediaJob;
}

export interface WorkerHeartbeatRequest {
  workerId: string;
  version: string;
}

export interface WorkerStatusResponse {
  online: boolean;
  workerId?: string;
  version?: string;
  lastSeen?: string;
}

export interface WorkerHeartbeatResponse {
  accepted: true;
  worker: WorkerStatusResponse;
}
