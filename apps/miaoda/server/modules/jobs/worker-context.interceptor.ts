import { CallHandler, ExecutionContext, Inject, Injectable, NestInterceptor } from '@nestjs/common';
import { DATAPAAS_CONFIG, DataPaasConfig, SqlExecutionContextMiddleware } from '@lark-apaas/fullstack-nestjs-core';
import { Observable, Subscription } from 'rxjs';

// Controller guards run first. Only authenticated Worker routes acquire the app's service context.
@Injectable()
export class WorkerContextInterceptor implements NestInterceptor {
  constructor(@Inject(DATAPAAS_CONFIG) private readonly config: DataPaasConfig) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return new Observable(subscriber => {
      const request = context.switchToHttp().getRequest();
      const response = context.switchToHttp().getResponse();
      request.userContext = {...request.userContext, isSystemAccount: true};
      let subscription: Subscription | undefined;
      new SqlExecutionContextMiddleware(this.config).use(request, response, () => {
        subscription = next.handle().subscribe(subscriber);
      });
      return () => subscription?.unsubscribe();
    });
  }
}
