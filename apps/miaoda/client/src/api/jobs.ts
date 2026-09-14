import axios, { type AxiosResponse } from 'axios';
import { logger } from '@lark-apaas/client-toolkit/logger';
import { axiosForBackend } from '@lark-apaas/client-toolkit/utils/getAxiosForBackend';

import type {
  CreateMediaJobRequest,
  ListMediaJobsResponse,
  MediaJobResponse,
  WorkerStatusResponse,
} from '@shared/api.interface';

interface ApiErrorBody {
  error?: {
    message?: string;
  };
}

const listMediaJobs = async (
  limit: number = 30,
): Promise<ListMediaJobsResponse> => {
  try {
    const response: AxiosResponse<ListMediaJobsResponse> =
      await axiosForBackend({
        url: '/api/jobs',
        method: 'GET',
        params: { limit },
      });
    return response.data;
  } catch (error: unknown) {
    logger.error('获取媒体任务失败', error);
    throw error;
  }
};

const createMediaJob = async (
  input: CreateMediaJobRequest,
): Promise<MediaJobResponse> => {
  try {
    const response: AxiosResponse<MediaJobResponse> = await axiosForBackend({
      url: '/api/jobs',
      method: 'POST',
      data: input,
    });
    return response.data;
  } catch (error: unknown) {
    logger.error('创建媒体任务失败', error);
    throw error;
  }
};

const retryMediaJob = async (id: string): Promise<MediaJobResponse> => {
  try {
    const response: AxiosResponse<MediaJobResponse> = await axiosForBackend({
      url: `/api/jobs/${id}/retry`,
      method: 'POST',
    });
    return response.data;
  } catch (error: unknown) {
    logger.error('重新排队媒体任务失败', error);
    throw error;
  }
};

const getWorkerStatus = async (): Promise<WorkerStatusResponse> => {
  try {
    const response: AxiosResponse<WorkerStatusResponse> = await axiosForBackend(
      {
        url: '/api/jobs/worker-status',
        method: 'GET',
      },
    );
    return response.data;
  } catch (error: unknown) {
    logger.error('获取 Worker 状态失败', error);
    throw error;
  }
};

const getApiErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data?.error?.message || '请求失败，请稍后重试';
  }
  if (error instanceof Error && error.message) return error.message;
  return '请求失败，请稍后重试';
};

export {
  createMediaJob,
  getApiErrorMessage,
  getWorkerStatus,
  listMediaJobs,
  retryMediaJob,
};
