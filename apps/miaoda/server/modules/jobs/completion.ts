// Local completion requires evidence of saved output, independently of optional remote delivery.
export function validateCompletion(workflow: string, outputName?: string | null): void {
  if (workflow !== 'inspect' && !outputName?.trim()) {
    throw new Error('下载任务完成时必须提供电脑已保存的文件名');
  }
}
