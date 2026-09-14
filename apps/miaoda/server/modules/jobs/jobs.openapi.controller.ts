import {
  Body,
  Controller,
  Get,
  Post,
  Query,
  UseGuards,
  UseInterceptors,
} from '@nestjs/common';

import type {
  ClaimMediaJobResponse,
  UpdateMediaJobResponse,
  WorkerHeartbeatResponse,
} from '@shared/api.interface';

import { UpdateMediaJobDto, WorkerHeartbeatDto } from './jobs.dto';
import { JobsService } from './jobs.service';
import { WorkerGuard } from './worker.guard';
import { WorkerContextInterceptor } from './worker-context.interceptor';

@Controller('openapi/jobs')
@UseGuards(WorkerGuard)
@UseInterceptors(WorkerContextInterceptor)
class OpenApiJobsController {
  constructor(private readonly jobsService: JobsService) {}

  @Get('next')
  async claimNext(
    @Query('workerId') workerId: string,
  ): Promise<ClaimMediaJobResponse> {
    return this.jobsService.claimNext(workerId);
  }

  @Post('worker/heartbeat')
  async heartbeat(
    @Body() body: WorkerHeartbeatDto,
  ): Promise<WorkerHeartbeatResponse> {
    return this.jobsService.heartbeat(body);
  }

  @Post('update')
  async updateFromWorker(
    @Body() body: UpdateMediaJobDto,
  ): Promise<UpdateMediaJobResponse> {
    return this.jobsService.updateFromWorker(body);
  }
}

export { OpenApiJobsController };
