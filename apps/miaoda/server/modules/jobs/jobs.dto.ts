import {
  IsEnum,
  IsInt,
  IsISO8601,
  IsOptional,
  IsString,
  IsUrl,
  IsUUID,
  Length,
  Max,
  MaxLength,
  Min,
} from 'class-validator';

import type {
  CreateMediaJobRequest,
  MediaQuality,
  MediaWorkflow,
  UpdateMediaJobRequest,
  WorkerHeartbeatRequest,
  WorkerProgressStatus,
} from '@shared/api.interface';

enum WorkflowValidation {
  VIDEO = 'video',
  AUDIO = 'audio',
  INSPECT = 'inspect',
}

enum QualityValidation {
  BEST = 'best',
  P1080 = '1080',
  P720 = '720',
  P480 = '480',
}

enum WorkerStatusValidation {
  INSPECTING = 'inspecting',
  DOWNLOADING = 'downloading',
  UPLOADING = 'uploading',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

class CreateMediaJobDto implements CreateMediaJobRequest {
  @IsString()
  @IsUrl({ protocols: ['https'], require_protocol: true })
  @MaxLength(2048)
  sourceUrl!: string;

  @IsEnum(WorkflowValidation)
  workflow!: MediaWorkflow;

  @IsEnum(QualityValidation)
  quality!: MediaQuality;
}

class UpdateMediaJobDto implements UpdateMediaJobRequest {
  @IsUUID()
  jobId!: string;

  @IsString()
  @Length(1, 128)
  workerId!: string;

  @IsEnum(WorkerStatusValidation)
  status!: WorkerProgressStatus;

  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(100)
  progress?: number;

  @IsOptional()
  @IsString()
  @MaxLength(1000)
  title?: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  uploader?: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  durationSeconds?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  width?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  height?: number;

  @IsOptional()
  @IsString()
  @MaxLength(1000)
  outputName?: string;

  @IsOptional()
  @IsUrl({ protocols: ['https'], require_protocol: true })
  @MaxLength(4096)
  deliveryUrl?: string;

  @IsOptional()
  @IsISO8601()
  deliveryExpiresAt?: string;

  @IsOptional()
  @IsString()
  @MaxLength(4000)
  errorMessage?: string;
}

class WorkerHeartbeatDto implements WorkerHeartbeatRequest {
  @IsString()
  @Length(1, 128)
  workerId!: string;

  @IsString()
  @Length(1, 32)
  version!: string;
}

export { CreateMediaJobDto, UpdateMediaJobDto, WorkerHeartbeatDto };
