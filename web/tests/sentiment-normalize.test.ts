/**
 * 情绪分数双标度归一化测试（N2+I3, 2026-08-03）。
 *
 * 背景：后端两条管线并存——旧管线写 -100..+100 整数，新管线写
 * -1..+1 浮点。此前 detail 页有自己的归一化、卡片/抽屉 tooltip 直接
 * toFixed(2) 裸渲染、InstrumentDetail 情绪条直接 scaleX，同一个分数
 * 在四个界面四个样。统一到 utils/sentiment.ts 后锁定行为。
 */
import { describe, it, expect } from 'vitest';
import {
  normalizeSentimentScore,
  formatSentimentScore,
} from '@/utils/sentiment';

describe('normalizeSentimentScore 双标度', () => {
  it('-1..+1 浮点标度原样保留', () => {
    expect(normalizeSentimentScore(0.78)).toBeCloseTo(0.78);
    expect(normalizeSentimentScore(-0.35)).toBeCloseTo(-0.35);
    expect(normalizeSentimentScore(1)).toBe(1);
    expect(normalizeSentimentScore(-1)).toBe(-1);
    expect(normalizeSentimentScore(0)).toBe(0);
  });

  it('-100..+100 整数标度按比例缩小 100 倍', () => {
    expect(normalizeSentimentScore(78)).toBeCloseTo(0.78);
    expect(normalizeSentimentScore(-35)).toBeCloseTo(-0.35);
    expect(normalizeSentimentScore(100)).toBe(1);
    expect(normalizeSentimentScore(-100)).toBe(-1);
  });

  it('边界：|x| <= 2 视为浮点标度', () => {
    expect(normalizeSentimentScore(2)).toBe(2);
    expect(normalizeSentimentScore(-2)).toBe(-2);
    // 2.5 超出浮点标度 → 按整数标度处理
    expect(normalizeSentimentScore(2.5)).toBeCloseTo(0.025);
  });

  it('非有限输入回退为 0（中性）', () => {
    expect(normalizeSentimentScore(NaN)).toBe(0);
    expect(normalizeSentimentScore(Infinity)).toBe(0);
    expect(normalizeSentimentScore(-Infinity)).toBe(0);
  });
});

describe('formatSentimentScore 展示', () => {
  it('两种标度输出同一字符串', () => {
    expect(formatSentimentScore(0.78)).toBe('0.78');
    expect(formatSentimentScore(78)).toBe('0.78');
    expect(formatSentimentScore(-0.35)).toBe('-0.35');
    expect(formatSentimentScore(-35)).toBe('-0.35');
  });

  it('缺失/非法输入渲染 em-dash', () => {
    expect(formatSentimentScore(null)).toBe('—');
    expect(formatSentimentScore(undefined)).toBe('—');
    expect(formatSentimentScore(NaN)).toBe('—');
  });
});
