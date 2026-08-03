import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { Button } from 'antd';
import { LeftOutlined, RightOutlined, ReadOutlined, UnorderedListOutlined } from '@ant-design/icons';
import './styles.css';
import { digestApi, isDigestNotFound, digestRetry, DIGEST_STALE_TIME } from '@/api/digest';
import type { DigestReport, DigestStatus } from '@/api/digest';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ThemeTag from '@/components/ThemeTag';
import type { ThemeTagVariant } from '@/components/ThemeTag';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import Markdown from '@/components/Markdown';
import { formatDateTime } from '@/utils/datetime';

/**
 * 每日夜间 AI 综合研报（B6，2026-08-02）。
 *
 * 设计要点：
 * - 移动优先：核心场景是手机晨读。竖屏字号/行高/留白优先，
 *   桌面端正文轨收敛到 ~720px 居中（PageShell reading 语义在
 *   本页内联实现，因为还需要给目录留侧栏列）。
 * - 目录从 content_md 的 `##` 标题提取锚点；sections_json 仅用于
 *   给对应章节标注降级/失败状态（按 title 匹配）。
 * - 历史导航：上一篇/下一篇 = by-date ±1 天，URL ?date= 直达。
 */

const STATUS_META: Record<DigestStatus, { label: string; variant: ThemeTagVariant }> = {
  pending: { label: '生成中', variant: 'default' },
  running: { label: '生成中', variant: 'accent' },
  success: { label: '完整', variant: 'success' },
  partial: { label: '部分章节数据缺失', variant: 'warning' },
  failed: { label: '生成失败', variant: 'error' },
};

interface ContentSection {
  title: string;
  body: string;
  anchor: string;
}

/** 把 content_md 按 `## ` 二级标题切成可锚点定位的章节。 */
function splitContent(md: string): { intro: string; sections: ContentSection[] } {
  const lines = md.split('\n');
  const sections: ContentSection[] = [];
  const introLines: string[] = [];
  let current: ContentSection | null = null;

  const flush = () => {
    if (current) {
      current.body = current.body.trim();
      sections.push(current);
    }
  };

  for (const line of lines) {
    const m = /^##\s+(.+?)\s*$/.exec(line);
    if (m) {
      flush();
      current = {
        title: m[1].replace(/#+\s*$/, '').trim(),
        body: '',
        anchor: `digest-sec-${sections.length}`,
      };
    } else if (current) {
      current.body += `${line}\n`;
    } else {
      introLines.push(line);
    }
  }
  flush();

  return { intro: introLines.join('\n').trim(), sections };
}

function todayStr(): string {
  return dayjs().format('YYYY-MM-DD');
}

function scrollToAnchor(anchor: string) {
  const el = typeof document !== 'undefined' ? document.getElementById(anchor) : null;
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

interface TocProps {
  sections: ContentSection[];
  report: DigestReport;
}

function TocList({ sections, report }: TocProps) {
  // sections_json 仅作状态角标来源（按 title 匹配），锚点以 content_md 为准。
  const statusByTitle = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of report.sections_json ?? []) {
      map.set(s.title, s.status);
    }
    return map;
  }, [report.sections_json]);

  if (sections.length === 0) return null;
  return (
    <ul className="digest-toc__list">
      {sections.map((sec) => {
        const st = statusByTitle.get(sec.title);
        return (
          <li key={sec.anchor}>
            <button
              type="button"
              className="digest-toc__item"
              onClick={() => scrollToAnchor(sec.anchor)}
            >
              <span className="digest-toc__title">{sec.title}</span>
              {st === 'degraded' && <span className="digest-toc__dot digest-toc__dot--degraded" title="数据降级" />}
              {st === 'failed' && <span className="digest-toc__dot digest-toc__dot--failed" title="生成失败" />}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function Digest() {
  const [searchParams, setSearchParams] = useSearchParams();
  const dateParam = searchParams.get('date');
  // ?date=YYYY-MM-DD 按日取，否则取最新一篇；useQuery 放组件内便于 mock api 层
  const {
    data: report,
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['digest', 'report', dateParam ?? 'latest'],
    queryFn: () =>
      (dateParam ? digestApi.getByDate(dateParam) : digestApi.getLatest()).then((r) => r.data),
    staleTime: DIGEST_STALE_TIME,
    retry: digestRetry,
  });

  const { intro, sections } = useMemo(
    () => splitContent(report?.content_md ?? ''),
    [report?.content_md],
  );

  const goToDate = (date: string) => setSearchParams({ date });
  const goLatest = () => setSearchParams({});

  const currentDate = dateParam ?? report?.report_date ?? null;
  const shiftDate = (days: number) => {
    const base = currentDate ?? todayStr();
    goToDate(dayjs(base).add(days, 'day').format('YYYY-MM-DD'));
  };
  // 「下一篇」：已在最新（无 date 参数）或当前日期 >= 今天时不可点
  const nextDisabled = !dateParam || (currentDate != null && currentDate >= todayStr());

  const statusMeta = report ? STATUS_META[report.status] ?? STATUS_META.pending : null;

  return (
    <PageShell maxWidth="wide" className="digest-page">
      <PageHeader
        eyebrow="资讯与研究"
        title="每日研报"
        description="AI 综合全球市场、宏观与资讯的夜间研报，每日 6:30 发布"
        data-onboard="digest"
      />

      {isPending ? (
        <LoadingBlock size="lg" />
      ) : error && isDigestNotFound(error) ? (
        <Panel variant="default">
          <EmptyState
            icon={<ReadOutlined />}
            title="今日研报生成中"
            description="每日 6:30 发布，请稍后再来"
            action={
              dateParam ? (
                <Button type="primary" onClick={goLatest}>
                  查看最近一篇
                </Button>
              ) : undefined
            }
          />
        </Panel>
      ) : error ? (
        <Panel variant="default">
          <EmptyState
            title="研报加载失败"
            description="请稍后重试"
            action={<Button onClick={() => refetch()}>重试</Button>}
          />
        </Panel>
      ) : report ? (
        <>
          {/* 历史导航 */}
          <div className="digest-nav">
            <Button
              size="small"
              icon={<LeftOutlined />}
              onClick={() => shiftDate(-1)}
              aria-label="上一篇"
            >
              上一篇
            </Button>
            <span className="digest-nav__date tabular-nums">{currentDate}</span>
            <Button
              size="small"
              onClick={() => shiftDate(1)}
              disabled={nextDisabled}
              aria-label="下一篇"
            >
              下一篇
              <RightOutlined />
            </Button>
            {dateParam && (
              <Button size="small" type="link" onClick={goLatest}>
                回到最新
              </Button>
            )}
          </div>

          {/* 首屏：标题 + 状态徽章 + 摘要卡 */}
          <Panel variant="default" className="digest-hero">
            <div className="digest-hero__meta">
              {statusMeta && (
                <ThemeTag variant={statusMeta.variant}>{statusMeta.label}</ThemeTag>
              )}
              <span className="digest-hero__date tabular-nums">{report.report_date}</span>
            </div>
            <h2 className="digest-hero__title">{report.title}</h2>
            {report.summary_md && (
              <div className="digest-hero__summary prose-reading">
                <Markdown source={report.summary_md} />
              </div>
            )}
            <div className="digest-hero__foot">
              {report.llm_model && <span>模型 {report.llm_model}</span>}
              {report.finished_at && (
                <span>完成于 {formatDateTime(report.finished_at, 'YYYY-MM-DD HH:mm', '')}</span>
              )}
            </div>
          </Panel>

          {/* 移动端可折叠目录 */}
          {sections.length > 0 && (
            <details className="digest-toc digest-toc--mobile">
              <summary>
                <UnorderedListOutlined /> 目录（{sections.length} 个章节）
              </summary>
              <TocList sections={sections} report={report} />
            </details>
          )}

          <div className="digest-layout">
            {/* 桌面端粘性侧栏目录 */}
            {sections.length > 0 && (
              <aside className="digest-toc digest-toc--desktop" aria-label="章节目录">
                <div className="digest-toc__heading">目录</div>
                <TocList sections={sections} report={report} />
              </aside>
            )}

            {/* 正文 */}
            <article className="digest-body">
              {intro && (
                <div className="prose-reading digest-body__intro">
                  <Markdown source={intro} />
                </div>
              )}
              {sections.map((sec) => (
                <section key={sec.anchor} id={sec.anchor} className="digest-section">
                  <h2 className="digest-section__title">{sec.title}</h2>
                  <div className="prose-reading">
                    <Markdown source={sec.body} />
                  </div>
                </section>
              ))}
              {!intro && sections.length === 0 && (
                <EmptyState title="本篇研报暂无正文" />
              )}
            </article>
          </div>
        </>
      ) : null}
    </PageShell>
  );
}
