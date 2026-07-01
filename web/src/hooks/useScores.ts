import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import { scoreApi } from '@/api';
import type { ScoreTemplateCreate, ScoreTemplateUpdate } from '@/types/score';

export function useScores(params?: { template_id?: number; market?: string; category?: string; limit?: number }) {
  return useQuery({
    queryKey: ['scores', params],
    queryFn: () => scoreApi.list(params).then((r) => r.data),
    staleTime: 60_000,
  });
}

export function useScoreTemplates() {
  return useQuery({
    queryKey: ['score-templates'],
    queryFn: () => scoreApi.templates().then((r) => r.data),
    staleTime: 300_000,
  });
}

export function useInstrumentScore(code: string, templateId?: number) {
  return useQuery({
    queryKey: ['instrument-score', code, templateId],
    queryFn: () => scoreApi.get(code, { template_id: templateId }).then((r) => r.data),
    enabled: !!code,
  });
}

// --- Template mutations -----------------------------------------------------

function useInvalidateTemplates() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['score-templates'] });
  };
}

export function useCreateTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: (data: ScoreTemplateCreate) => scoreApi.createTemplate(data).then((r) => r.data),
    onSuccess: () => {
      message.success('模板已创建');
      invalidate();
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || err?.message || '创建失败';
      message.error(`创建失败：${detail}`);
    },
  });
}

export function useUpdateTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ScoreTemplateUpdate }) =>
      scoreApi.updateTemplate(id, data).then((r) => r.data),
    onSuccess: () => {
      message.success('模板已更新');
      invalidate();
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || err?.message || '更新失败';
      message.error(`更新失败：${detail}`);
    },
  });
}

export function useDeleteTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: (id: number) => scoreApi.deleteTemplate(id).then(() => id),
    onSuccess: () => {
      message.success('模板已删除');
      invalidate();
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || err?.message || '删除失败';
      message.error(`删除失败：${detail}`);
    },
  });
}
