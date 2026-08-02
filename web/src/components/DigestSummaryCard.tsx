import './DigestSummaryCard.css';

import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ReadOutlined } from '@ant-design/icons';
import { digestApi, isDigestNotFound, digestRetry, DIGEST_STALE_TIME } from '@/api/digest';
import LoadingBlock from '@/components/LoadingBlock';

/**
 * Dashboard「每日研报」摘要卡（B6，2026-08-02）。
 *
 * - 数据源：GET /digest/latest/summary（轻量，staleTime 5min，见 api/digest.ts）。
 * - 有报告：标题 + 日期 + 摘要前 3 行 + 「阅读全文 →」。
 * - 404（今日尚未生成）：降级态「今日研报生成中，每日 6:30 发布」。
 *
 * 卡片骨架复用 Dashboard command-center 的 cc-card 体系（视觉与
 * 周边卡片一致），内部布局样式在本组件 css 中自带（token 化），
 * 插入位置是 pulse-grid 与 cc-grid 之间的整宽条，不破坏现有网格。
 */

/** 把 summary_md 拍平成纯文本（去 markdown 记号），供 3 行摘要展示。 */
export function summaryToPlainText(md: string | null | undefined): string {
  if (!md) return '';
  return md
    .split('\n')
    .map((line) =>
      line
        .replace(/^\s{0,3}#{1,6}\s+/, '') // 标题
        .replace(/^\s*[-*+]\s+/, '') // 无序列表
        .replace(/^\s*\d+[.)、]\s+/, '') // 有序列表
        .replace(/^\s*>\s?/, '') // 引用
        .replace(/[*_`~]/g, '') // 强调/代码记号
        .trim(),
    )
    .filter(Boolean)
    .slice(0, 3)
    .join('；');
}

export default function DigestSummaryCard() {
  const navigate = useNavigate();
  // 轻量摘要（staleTime 5min）；useQuery 放在组件内以便测试 mock api 层
  const { data, isPending, error } = useQuery({
    queryKey: ['digest', 'latest-summary'],
    queryFn: () => digestApi.getLatestSummary().then((r) => r.data),
    staleTime: DIGEST_STALE_TIME,
    retry: digestRetry,
  });

  const goDigest = () => navigate('/digest');
  const notFound = error != null && isDigestNotFound(error);

  return (
    <section className="cc-card digest-summary-card" aria-label="每日研报">
      <div className="cc-card__header">
        <div>
          <div className="cc-card__title">
            <ReadOutlined className="digest-summary-card__icon" aria-hidden="true" /> 每日研报
          </div>
          <div className="cc-card__subtitle">
            {data ? `${data.report_date} · AI 夜间综合研报` : 'AI 夜间综合研报'}
          </div>
        </div>
        {data && (
          <span
            className="cc-card__extra"
            onClick={goDigest}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                goDigest();
              }
            }}
            role="button"
            tabIndex={0}
          >
            阅读全文 →
          </span>
        )}
      </div>

      {isPending ? (
        <LoadingBlock size="sm" />
      ) : notFound ? (
        <div className="digest-summary-card__pending">
          今日研报生成中，每日 6:30 发布
        </div>
      ) : error ? (
        <div className="digest-summary-card__pending">研报摘要加载失败，请稍后重试</div>
      ) : data ? (
        <div
          className="digest-summary-card__body"
          onClick={goDigest}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              goDigest();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label={`阅读每日研报全文：${data.title}`}
        >
          <div className="digest-summary-card__headline">{data.title}</div>
          <p className="digest-summary-card__excerpt">
            {summaryToPlainText(data.summary_md) || '点击查看今日研报全文'}
          </p>
        </div>
      ) : null}
    </section>
  );
}
