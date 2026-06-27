import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { poolApi } from '@/api';
import type { PoolUpdate } from '@/types/pool';

export function usePoolList() {
  return useQuery({
    queryKey: ['pools'],
    queryFn: () => poolApi.list().then((r) => r.data),
    staleTime: 60_000,
  });
}

export function usePoolDetail(id: number) {
  return useQuery({
    queryKey: ['pool', id],
    queryFn: () => poolApi.get(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function usePoolWeights(id: number) {
  return useQuery({
    queryKey: ['pool-weights', id],
    queryFn: () => poolApi.weights(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function usePoolAnalytics(id: number) {
  return useQuery({
    queryKey: ['pool-analytics', id],
    queryFn: () => poolApi.analytics(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function usePoolCorrelation(id: number) {
  return useQuery({
    queryKey: ['pool-correlation', id],
    queryFn: () => poolApi.correlation(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function usePoolSnapshots(id: number, limit?: number) {
  return useQuery({
    queryKey: ['pool-snapshots', id, limit],
    queryFn: () => poolApi.snapshots(id, limit).then((r) => r.data),
    enabled: !!id,
  });
}

export function useCreateSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (poolId: number) => poolApi.createSnapshot(poolId),
    onSuccess: (_, poolId) => {
      qc.invalidateQueries({ queryKey: ['pool-snapshots', poolId] });
    },
  });
}

export function useSuggestWeights() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ poolId, algorithm, templateId }: { poolId: number; algorithm: string; templateId?: number }) =>
      poolApi.suggestWeights(poolId, algorithm, templateId),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['pool-weights', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-analytics', vars.poolId] });
    },
  });
}

export function useUpdateWeight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ poolId, code, weight }: { poolId: number; code: string; weight: number }) =>
      poolApi.updateWeight(poolId, code, weight),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['pool-weights', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-analytics', vars.poolId] });
    },
  });
}

export function useUpdatePool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ poolId, data }: { poolId: number; data: PoolUpdate }) =>
      poolApi.update(poolId, data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['pool', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pools'] });
    },
  });
}

export function useAddPoolMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ poolId, etf_code }: { poolId: number; etf_code: string }) =>
      poolApi.addMember(poolId, etf_code),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['pool', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-weights', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-analytics', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-correlation', vars.poolId] });
    },
  });
}

export function useRemovePoolMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ poolId, etf_code }: { poolId: number; etf_code: string }) =>
      poolApi.removeMember(poolId, etf_code),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['pool', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-weights', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-analytics', vars.poolId] });
      qc.invalidateQueries({ queryKey: ['pool-correlation', vars.poolId] });
    },
  });
}
