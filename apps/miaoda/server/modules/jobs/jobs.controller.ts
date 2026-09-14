import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';
import { NeedLogin } from '@lark-apaas/fullstack-nestjs-core';

import type {
  ListMediaJobsResponse,
  MediaJobResponse,
  WorkerStatusResponse,
} from '@shared/api.interface';

import { CreateMediaJobDto } from './jobs.dto';
import { JobsService } from './jobs.service';

@Controller('api/jobs')
class JobsController {
  constructor(private readonly jobsService: JobsService) {}

  @NeedLogin()
  @Get()
  async list(
    @Query('limit') limitInput?: string,
  ): Promise<ListMediaJobsResponse> {
    const parsed: number = Number.parseInt(limitInput ?? '30', 10);
    const limit: number = Number.isFinite(parsed)
      ? Math.min(Math.max(parsed, 1), 100)
      : 30;
    return this.jobsService.list(limit);
  }

  @NeedLogin()
  @Get('worker-status')
  async getWorkerStatus(): Promise<WorkerStatusResponse> {
    return this.jobsService.getWorkerStatus();
  }

  @NeedLogin()
  @Post()
  async create(@Body() body: CreateMediaJobDto): Promise<MediaJobResponse> {
    return this.jobsService.create(body);
  }

  @NeedLogin()
  @Post(':id/retry')
  async retry(@Param('id') id: string): Promise<MediaJobResponse> {
    return this.jobsService.retry(id);
  }
}

export { JobsController };
