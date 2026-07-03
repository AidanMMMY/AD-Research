import { useEffect, useMemo, useState } from 'react';
import { Button, Tag, Space } from 'antd';
import {
  BookOutlined,
  BulbOutlined,
  RocketOutlined,
  CheckOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getAllTerms } from '@/utils/termDictionary';
import {
  pickDailyTermKey,
  useLearnedTerms,
} from '@/hooks/useLearnedTerms';
import { useAIHelp } from '@/hooks/useAIHelp';

interface DailyLessonProps {
  /**
   * Allow injection for tests; by default uses `new Date()` so the lesson
   * rotates daily with no extra state.
   */
  today?: Date;
}

function todayKey(d: Date): string {
  // Local-time YYYY-MM-DD key.  Used both as a daily rotation seed and as a
  // localStorage namespace so the chosen term persists across reloads.
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * K15 P0: Dashboard "今日学习 3 分钟" 卡片。
 * - 每天（按本地日期做 hash）从 termDictionary 抽 1 个词条，保证稳定；
 * - 提供"展开/收起"、"问 AI"、"我学会了"三个动作；
 * - 通过 useLearnedTerms 与 dashboard 的周统计复用。
 *
 * 设计取舍：用纯前端组件，不写新 store / 不引入新接口。
 */
export default function DailyLesson({ today = new Date() }: DailyLessonProps) {
  const navigate = useNavigate();
  const { open: openAIHelp } = useAIHelp();
  const learned = useLearnedTerms();

  const allTerms = useMemo(() => getAllTerms(), []);
  const dateKey = useMemo(() => todayKey(today), [today]);

  const term = useMemo(() => {
    if (allTerms.length === 0) return null;
    const remembered = learned.lessonShownFor(dateKey);
    if (remembered) {
      return allTerms.find((t) => t.key === remembered) ?? null;
    }
    const keys = allTerms.map((t) => t.key);
    const picked = pickDailyTermKey(dateKey, keys);
    if (picked) learned.rememberLessonFor(dateKey, picked);
    return allTerms.find((t) => t.key === picked) ?? null;
  }, [allTerms, dateKey, learned]);

  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    // Reset expanded state when day changes.
    setExpanded(false);
  }, [dateKey]);

  if (!term) return null;

  const isLearned = learned.has(term.key);

  const openAsk = () => {
    openAIHelp({
      pageType: term.relatedPageType ?? 'instrument_detail',
      pageTitle: `每日学习 - ${term.title}`,
      contextData: `用户正在学习术语「${term.title}」。\n${term.fullDesc}`,
      initialQuestion: `我是一个新手，请先用一个生活中的类比解释「${term.title}」，再讲它在投资中的实际意义。`,
      quickQuestions: [
        `「${term.title}」的数值高低代表什么？`,
        `如何在投资中用「${term.title}」做判断？`,
        `这个概念有什么常见误区？`,
        '能不能用更简单的语言再解释一遍？',
      ],
    });
  };

  return (
    <section className="daily-lesson panel--elevated">
      <div className="daily-lesson__header">
        <div className="daily-lesson__title-row">
          <BookOutlined className="daily-lesson__icon" />
          <div className="daily-lesson__title">今日学习 3 分钟</div>
          <Tag color="blue">每天 1 个概念</Tag>
          {isLearned && (
            <Tag icon={<CheckOutlined />} color="success">
              已学会
            </Tag>
          )}
        </div>
        <div className="daily-lesson__date">{dateKey}</div>
      </div>

      <div className="daily-lesson__body">
        <div className="daily-lesson__heading">
          <RocketOutlined className="daily-lesson__heading-icon" />
          <span className="daily-lesson__heading-title">{term.title}</span>
        </div>
        <p className="daily-lesson__short">{term.shortDesc}</p>
        {expanded && (
          <div className="daily-lesson__full">
            <p>{term.fullDesc}</p>
            {term.formula && (
              <div className="daily-lesson__formula">
                <span className="daily-lesson__caption">公式</span>
                <code>{term.formula}</code>
              </div>
            )}
            {term.example && (
              <div className="daily-lesson__example">
                <span className="daily-lesson__caption">
                  <BulbOutlined /> 举个例子
                </span>
                <span>{term.example}</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="daily-lesson__actions">
        <Space wrap>
          <Button size="small" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '收起' : '展开看完整说明'}
          </Button>
          <Button size="small" type="primary" onClick={openAsk}>
            问 AI
          </Button>
          {!isLearned && (
            <Button
              size="small"
              icon={<CheckOutlined />}
              onClick={() => learned.mark(term.key)}
            >
              我学会了
            </Button>
          )}
          {isLearned && (
            <Button
              size="small"
              icon={<ArrowRightOutlined />}
              onClick={() => navigate('/learning')}
            >
              去新手教程
            </Button>
          )}
        </Space>
        <div className="daily-lesson__hint">
          本周已学习 <b>{learned.thisWeek}</b> 个术语
        </div>
      </div>
    </section>
  );
}
