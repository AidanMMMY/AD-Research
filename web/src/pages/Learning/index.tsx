import { useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Tag, Space, Button, Collapse, Input } from 'antd';
import {
  ReadOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  ArrowRightOutlined,
  PartitionOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import { useSettingsStore } from '@/stores/settings';
import './styles.css';
import { getAllTerms, type TermEntry } from '@/utils/termDictionary';

interface Scenario {
  id: string;
  title: string;
  tagline: string;
  steps: string[];
  /** Optional CTA: jump to a page after opening AI Help. */
  jumpTo?: { path: string; label: string };
  /** Optional AI Help initial question (kept as static text — no LLM call). */
  initialQuestion: string;
  tags: string[];
  icon: React.ReactNode;
  estimatedMinutes: number;
}

const SCENARIOS: Scenario[] = [
  {
    id: 'valuation',
    title: '如何看懂 1 个 ETF 的估值',
    tagline: '从行情页到研究笔记，建立你的第一个分析流程',
    estimatedMinutes: 5,
    tags: ['新手友好', 'ETF 入门'],
    icon: <ReadOutlined />,
    steps: [
      '在首页挑一个你关注的 ETF，点击进入「标的详情」。',
      '查看综合评分与 1 月 / 3 月 / 1 年收益，了解近期表现。',
      '看估值相关字段（PE / PB / ROE）判断当前位置。',
      '滚动到「AI 研究笔记」，点生成查看结构化解读。',
      '点击右上角「问 AI」，追问「这只 ETF 当前估值偏高还是偏低？」',
    ],
    jumpTo: { path: '/screen', label: '先去选股器找一只 ETF' },
    initialQuestion: '我是一个新手，请用一个例子带我理解「估值高低」到底指什么。',
  },
  {
    id: 'macro-follow',
    title: '怎么跟踪 1 次央行决议对 A 股的影响',
    tagline: '把宏观、情绪、信号串成一条故事线',
    estimatedMinutes: 7,
    tags: ['宏观', 'A 股'],
    icon: <LineChartOutlined />,
    steps: [
      '打开「宏观经济」，先看 SHIBOR / M2 / CPI 最近 3 个月走势。',
      '切到「市场情绪」，对比决议前后情绪分数变化。',
      '切到「交易信号」，观察决议后 1-3 个交易日买入信号是否增多。',
      '回到任一受影响板块的 ETF 详情，看估值与回撤是否同步变化。',
      '把上面的发现写到 AI 研究笔记，下次复盘用。',
    ],
    jumpTo: { path: '/macro', label: '打开宏观经济看板' },
    initialQuestion: '央行加息或降息是怎么一步步传导到 A 股的？请用最简单的语言讲一遍。',
  },
  {
    id: 'full-backtest',
    title: '怎么做一次完整的策略回测',
    tagline: '从策略模板到净值曲线，5 步搞定',
    estimatedMinutes: 10,
    tags: ['回测', '策略'],
    icon: <ExperimentOutlined />,
    steps: [
      '到「策略库」挑选一个模板（动量 / 均值回归 / RSI）。',
      '回到「策略管理」，点「基于模板新建」，命名并启用。',
      '到「回测管理」新建一个回测任务，选刚才的策略 + 时间窗口。',
      '等待回测完成，打开「回测详情」查看年化、夏普、最大回撤、净值曲线。',
      '点策略详情看交易记录，复盘哪几笔最赚、哪几笔最亏。',
    ],
    jumpTo: { path: '/strategy-library', label: '打开策略库' },
    initialQuestion: '回测里的「夏普比率」和「最大回撤」分别代表什么？我应该重点看哪个？',
  },
];

export default function Learning() {
  const navigate = useNavigate();
  const location = useLocation();

  // M20: 当从 Dashboard 「查看知识图谱」chip 跳过来时，自动展开「术语速查」面板。
  const wantsTermsPanel = useMemo(
    () => new URLSearchParams(location.search).get('panel') === 'terms',
    [location.search]
  );
  const [panelOpen, setPanelOpen] = useState(wantsTermsPanel);
  // Adjust state during render (React docs pattern) instead of a
  // setState-in-effect: re-open the panel when the user re-arrives
  // with ?panel=terms.
  const [prevWantsTermsPanel, setPrevWantsTermsPanel] = useState(wantsTermsPanel);
  if (wantsTermsPanel !== prevWantsTermsPanel) {
    setPrevWantsTermsPanel(wantsTermsPanel);
    if (wantsTermsPanel) setPanelOpen(true);
  }

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="教学"
        title="新手教程"
        description="围绕几个真实场景，把平台的关键页面串起来。挑一个最关心的开始。"
      />

      <div className="learning-scenarios">
        {SCENARIOS.map((s) => (
          <ScenarioCard key={s.id} scenario={s} onJump={navigate} />
        ))}
      </div>

      {/* M20: 知识图谱入口 — 折叠面板形式的术语速查。
          P2 将升级为真正的图谱视图。 */}
      <div className="learning-terms-wrap ad-mt-5">
        <Space className="ad-mb-2">
          <Button
            type={panelOpen ? 'primary' : 'default'}
            icon={<PartitionOutlined />}
            onClick={() => setPanelOpen((v) => !v)}
            aria-expanded={panelOpen}
            aria-controls="learning-terms-region"
          >
            {panelOpen ? '收起术语速查' : '展开术语速查'}
          </Button>
          <span className="ad-text-small ad-text-tertiary">
            知识图谱入口（M20）
          </span>
        </Space>

        {/* Spatial consistency: the panel stays mounted so height/opacity
            animate from the live size on close — no jump, no reflow. The
            `aria-hidden` mirror communicates the closed state to AT. */}
        <div
          id="learning-terms-region"
          className={`learning-terms-region ${panelOpen ? 'learning-terms-region--open' : 'learning-terms-region--closed'}`}
          aria-hidden={!panelOpen}
        >
          <TermQuickReference initialOpen={wantsTermsPanel} />
        </div>
      </div>
    </PageShell>
  );
}

/**
 * M20: 把每条 TermEntry 的 `relatedPageType` 翻译成顶层分类标签，
 * 方便把 entry 按"所属知识域"分组展示。
 * 不相关时落到 "其他" 一组，避免信息丢失。
 */
function bucketOf(entry: TermEntry): string {
  switch (entry.relatedPageType) {
    case 'score_ranking':
      return '评分体系';
    case 'instrument_detail':
      return '标的 / 行情';
    case 'strategy_list':
      return '策略';
    case 'backtest_detail':
      return '回测';
    case 'screen':
      return '筛选';
    case 'pool_detail':
      return '标的池';
    case 'signal_dashboard':
      return '交易信号';
    case 'listing_preview':
      return '上市预告';
    default:
      return '其他';
  }
}

/**
 * M20: 术语速查面板 — 当前期是把 termDictionary 的全部 entry
 * 按一级分组渲染成可搜索列表，标题 hover 触发 HelpPopover。
 * P2 将升级为真正的知识图谱视图。
 */
function TermQuickReference({
  initialOpen,
}: {
  initialOpen: boolean;
}) {
  const mode = useSettingsStore((s) => s.mode);
  const [keyword, setKeyword] = useState('');
  const all = useMemo(() => getAllTerms(), []);

  const grouped = useMemo(() => {
    const map = new Map<string, TermEntry[]>();
    const lower = keyword.trim().toLowerCase();
    for (const e of all) {
      if (lower) {
        const hay = `${e.title} ${e.shortDesc} ${e.key}`.toLowerCase();
        if (!hay.includes(lower)) continue;
      }
      const b = bucketOf(e);
      const list = map.get(b) ?? [];
      list.push(e);
      map.set(b, list);
    }
    // 组内按 title 排序
    for (const [b, list] of map.entries()) {
      list.sort((a, b2) => a.title.localeCompare(b2.title, 'zh-Hans-CN'));
      map.set(b, list);
    }
    return map;
  }, [all, keyword]);

  const totalShown = Array.from(grouped.values()).reduce(
    (acc, list) => acc + list.length,
    0
  );

  const collapseItems = Array.from(grouped.entries()).map(([bucket, list]) => ({
    key: bucket,
    label: (
      <Space>
        <span>{bucket}</span>
        <Tag>{list.length}</Tag>
      </Space>
    ),
    children: (
      <ul className="learning-terms__list">
        {list.map((t) => (
          <li key={t.key} className="learning-terms__item">
            <HelpPopover termKey={t.key} mode={mode}>
              <span className="learning-terms__title">{t.title}</span>
            </HelpPopover>
            <span className="learning-terms__desc">{t.shortDesc}</span>
          </li>
        ))}
      </ul>
    ),
  }));

  return (
    <Panel
      variant="default"
      padding="md"
      className="learning-terms"
      title={
        <Space>
          <PartitionOutlined className="ad-text-accent" />
          <span>术语速查</span>
          <ThemeTag variant="warning">M20 P1</ThemeTag>
        </Space>
      }
      extra={
        <Input
          allowClear
          size="small"
          prefix={<SearchOutlined />}
          placeholder="按名称 / 描述 / key 过滤"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="learning__filter-input"
        />
      }
    >
      <p className="ad-text-small ad-text-tertiary ad-mt-0">
        共 {all.length} 个术语，当前显示 {totalShown} 个。鼠标悬停或点击标题可看「问 AI」浮层。
        P2 将升级为真正的图谱视图。
      </p>
      {totalShown === 0 ? (
        <EmptyState title="没有匹配的术语" />
      ) : (
        <Collapse
          defaultActiveKey={initialOpen ? [Array.from(grouped.keys())[0]] : []}
          items={collapseItems}
        />
      )}
    </Panel>
  );
}

function ScenarioCard({
  scenario,
  onJump,
}: {
  scenario: Scenario;
  onJump: (path: string) => void;
}) {
  return (
    <Panel variant="default" padding="md" className="learning-scenario-card">
      <div className="learning-scenario-card__head">
        <div className="learning-scenario-card__icon">{scenario.icon}</div>
        <div className="learning-scenario-card__heading">
          <div className="learning-scenario-card__title">{scenario.title}</div>
          <div className="learning-scenario-card__tagline">{scenario.tagline}</div>
        </div>
        <div className="learning-scenario-card__meta">
          <ThemeTag variant="accent">约 {scenario.estimatedMinutes} 分钟</ThemeTag>
          {scenario.tags.map((t) => (
            <Tag key={t}>{t}</Tag>
          ))}
        </div>
      </div>

      <ol className="learning-scenario-card__steps">
        {scenario.steps.map((step, idx) => (
          <li key={idx} className="learning-scenario-card__step">
            <span className="learning-scenario-card__step-num">{idx + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>

      <div className="learning-scenario-card__cta">
        <Space wrap className="learning-scenario-card__cta-buttons">
          {scenario.jumpTo && (
            <Button
              type="primary"
              icon={<ArrowRightOutlined />}
              onClick={() => onJump(scenario.jumpTo!.path)}
            >
              {scenario.jumpTo.label}
            </Button>
          )}
          <Button
            type="default"
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent('ad-research:reopen-onboarding')
              );
            }}
          >
            回到 5 步新手引导
          </Button>
        </Space>
        <div className="learning-scenario-card__initial-q">
          <span className="learning-scenario-card__initial-q-label">
            推荐先问 AI：
          </span>
          <span className="learning-scenario-card__initial-q-text">
            {scenario.initialQuestion}
          </span>
        </div>
      </div>
    </Panel>
  );
}