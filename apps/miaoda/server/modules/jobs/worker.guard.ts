import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { timingSafeEqual } from 'node:crypto';

@Injectable()
export class WorkerGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const expected = process.env.MEDIA_WORKER_API_KEY ?? '';
    const request = context.switchToHttp().getRequest<{ headers: Record<string, string | undefined> }>();
    const received = request.headers.authorization?.match(/^Bearer (.+)$/iu)?.[1] ?? '';
    const left = Buffer.from(received);
    const right = Buffer.from(expected);
    if (!expected || left.length !== right.length || !timingSafeEqual(left, right)) {
      throw new UnauthorizedException('Worker Key 未配置或不正确');
    }
    return true;
  }
}
