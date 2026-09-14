import { Module } from '@nestjs/common';

import { JobsController } from './jobs.controller';
import { OpenApiJobsController } from './jobs.openapi.controller';
import { JobsService } from './jobs.service';

@Module({
  controllers: [JobsController, OpenApiJobsController],
  providers: [JobsService],
})
class JobsModule {}

export { JobsModule };
