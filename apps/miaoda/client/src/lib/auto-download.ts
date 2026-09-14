import type { MediaJob } from '@shared/api.interface';

export interface DownloadQueue {
  remember: (id: string) => void;
  inspect: (jobs: MediaJob[]) => Promise<void>;
}

export const saveToDevice = async (url: string, name: string): Promise<void> => {
  if (new URL(url).protocol !== 'https:') throw new Error('下载地址必须是 HTTPS');
  // A Blob URL lets the browser honor the filename even when OSS is on another origin.
  const response = await fetch(url, { credentials: 'omit' });
  if (!response.ok) throw new Error(`文件下载失败（HTTP ${response.status}）`);
  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = name || 'media-download';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
};

export const createDownloadQueue = (
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  key: string,
  save: (url: string, name: string) => Promise<void>,
  notify: (message: string, failed: boolean) => void,
): DownloadQueue => {
  let remembered: string[] = [];
  try {
    const data: unknown = JSON.parse(storage.getItem(key) || '[]');
    if (Array.isArray(data)) remembered = data.filter((id): id is string => typeof id === 'string');
  } catch { /* Private browsing may disable session storage. Keep in-memory behavior. */ }
  const pending = new Set(remembered);
  const active = new Set<string>();
  const persist = (): void => {
    try { storage.setItem(key, JSON.stringify([...pending])); } catch { /* In-memory queue remains valid. */ }
  };
  return {
    remember(id) { pending.add(id); persist(); },
    async inspect(jobs) {
      for (const job of jobs) {
        if (!pending.has(job.id) || active.has(job.id)) continue;
        if (job.status === 'failed') { pending.delete(job.id); persist(); continue; }
        if (job.status !== 'completed') continue;
        active.add(job.id);
        try {
          if (job.workflow !== 'inspect' && job.deliveryUrl) {
            notify('文件已准备好，正在下载到当前设备…', false);
            await save(job.deliveryUrl, job.outputName || 'media-download');
            notify('已交给浏览器保存，请查看下载列表', false);
          } else if (job.workflow !== 'inspect') {
            notify('已保存到下载电脑；当前使用本地保存模式', false);
          }
        } catch {
          notify('自动下载未完成，可在最近任务点击“下载文件”重试', true);
        } finally {
          pending.delete(job.id);
          active.delete(job.id);
          persist();
        }
      }
    },
  };
};
