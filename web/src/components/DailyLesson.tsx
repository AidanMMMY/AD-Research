import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Tag } from 'antd';
import {
  BulbOutlined,
  CheckOutlined,
  ArrowRightOutlined,
  SyncOutlined,
  BookOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  LESSON_BANK,
  pickLesson,
  type LessonEntry,
} from '@/utils/lessonBank';
import { useLearnedTerms } from '@/hooks/useLearnedTerms';
import { useAIHelp } from '@/hooks/useAIHelp';

interface DailyLessonProps {
  /** Backwards-compat test hook — ignored by the live UI. */
  today?: Date;
}

/**
 * K15 P0 + Phase 2 (2026-07-07): Dashboard "今日学习" lesson card.
 *
 * Phase 2 changes:
 *   - Drops the inner panel surface (was a deep blue gradient with a
 *     hard border). New visual uses ``--bg-elevated`` background,
 *     ``--border-default`` 1px line, ``--radius-lg`` corners — light,
 *     neutral, and consistent with the rest of the dashboard.
 *   - Replaced the termDictionary pick (heavy 200+ entry weight) with
 *     a hand-curated ``lessonBank`` (12 conversational lessons). The
 *     termDictionary still powers HelpPopover elsewhere.
 *   - Layout is a single column: header (title + learned tag), body
 *     (category tag + lesson title + content + tip), and footer
 *     (weekly progress hint + action buttons).
 *   - "No-repeat this session" tracked via useRef Set of lesson IDs.
 *
 * The component never renders its own border — the Dashboard still
 * hosts it inside a Panel, so the visual nesting stays single-level.
 */
export default function DailyLesson({ today: _today = new Date() }: DailyLessonProps) {
  const navigate = useNavigate();
  const { open: openAIHelp } = useAIHelp();
  const learned = useLearnedTerms();

  // Session-scoped dedup set: lesson IDs already shown this page mount.
  // Reset only when the component unmounts (no per-day lock — user
  // expects to keep getting fresh lessons on every shuffle / revisit).
  const shownRef = useRef<Set<string>>(new Set());

  const pickFresh = useCallback((): LessonEntry | null => {
    const lesson = pickLesson(LESSON_BANK, shownRef.current);
    if (lesson) shownRef.current.add(lesson.id);
    return lesson;
  }, []);

  const [lesson, setLesson] = useState<LessonEntry | null>(() => pickFresh());

  // Defensive: if the bank ever changes shape and we mounted with null,
  // retry once on the next tick.
  useEffect(() => {
    if (!lesson) {
      const l = pickFresh();
      if (l) setLesson(l);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const shuffle = useCallback(() => {
    setLesson((prev) => {
      // Avoid showing the same lesson twice in a row on explicit shuffle.
      let next: LessonEntry | null = null;
      for (let i = 0; i < 6; i++) {
        const candidate = pickFresh();
        if (!candidate) break;
        if (!prev || candidate.id !== prev.id) {
          next = candidate;
          break;
        }
      }
      if (!next) next = pickFresh();
      return next;
    });
  }, [pickFresh]);

  if (!lesson) return null;

  const isLearned = learned.has(lesson.id);

  const openAsk = () => {
    openAIHelp({
      pageType: 'instrument_detail',
      pageTitle: `每日学习 - ${lesson.title}`,
      contextData: `用户正在阅读 Dashboard「今日一课」卡片。\n主题：${lesson.title}\n分类：${lesson.tag}\n正文：${lesson.body}\n${lesson.tip ? `\n要点：${lesson.tip}` : ''}`,
      initialQuestion: `请先用一个生活中的类比解释「${lesson.title}」，再讲它在投资中的实际意义。`,
      quickQuestions: [
        `「${lesson.title}」在投资里最常见的应用场景是什么？`,
        `有没有什么常见误区？`,
        `能不能用更简单的语言再解释一遍？`,
      ],
    });
  };

  return (
    <section className="daily-lesson">
      <div className="daily-lesson__header">
        <div className="daily-lesson__title-row">
          <BookOutlined className="daily-lesson__icon" />
          <span className="daily-lesson__title">今日一课</span>
        </div>
        {isLearned && (
          <Tag icon={<CheckOutlined />} color="success" className="daily-lesson__tag">
            已学会
          </Tag>
        )}
      </div>

      <div className="daily-lesson__body">
        <div className="daily-lesson__col daily-lesson__col--main">
          <div className="daily-lesson__heading">
            <Tag className="daily-lesson__tag">{lesson.tag}</Tag>
            <span className="daily-lesson__heading-title">{lesson.title}</span>
          </div>
          <p className="daily-lesson__short">{lesson.body}</p>
          {lesson.tip && (
            <div className="daily-lesson__tip">
              <BulbOutlined className="daily-lesson__tip-icon" />
              <span>{lesson.tip}</span>
            </div>
          )}
        </div>
      </div>

      <div className="daily-lesson__footer">
        <div className="daily-lesson__hint">
          <span>本周已学习 <b>{learned.thisWeek}</b> 个概念</span>
          <span className="daily-lesson__divider">·</span>
          <span className="daily-lesson__hint-sub">每次进入页面随机抽取</span>
        </div>
        <div className="daily-lesson__actions">
          <Button
            size="small"
            type="primary"
            icon={<SyncOutlined />}
            onClick={shuffle}
            aria-label="换一个概念"
          >
            换一题
          </Button>
          <Button size="small" onClick={openAsk}>
            问 AI
          </Button>
          {!isLearned ? (
            <Button
              size="small"
              icon={<CheckOutlined />}
              onClick={() => learned.mark(lesson.id)}
            >
              已学会
            </Button>
          ) : (
            <Button
              size="small"
              icon={<ArrowRightOutlined />}
              onClick={() => navigate('/learning')}
            >
              去教程
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}