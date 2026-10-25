/**
 * 全球市场时段工具（Aurora Horizon 设计语言共享逻辑，2026-10-25）。
 *
 * 「晨昏线」：多市场平台横跨时区，太阳永远在某处交易。色相 = 当前时段
 * 状态（氛围即信息）。登录页观测台与 Dashboard 指挥中心共用本模块，
 * 保证两边永远显示同一个世界。
 *
 * 时段/开市判定取整点近似（足够传达状态语义，不追求交易所级日历精度）。
 */

export interface SessionPhase {
  label: string;
  sub: string;
  /** 晨昏线色相锚点（写入 CSS --horizon-h） */
  hue: number;
}

export function getSessionPhase(now: Date = new Date()): SessionPhase {
  const day = now.getDay();
  const h = now.getHours();
  if (day === 0 || day === 6) return { label: '周末休市', sub: '隔夜市场数据整备中', hue: 260 };
  if (h >= 9 && h < 15) return { label: '东京时段', sub: 'A 股连续竞价', hue: 38 };
  if (h >= 15 && h < 21) return { label: '欧洲时段', sub: '法兰克福 · 伦敦', hue: 175 };
  if (h >= 21 || h < 5) return { label: '纽约时段', sub: '美股交易中', hue: 200 };
  return { label: '休市间隙', sub: '盘前数据整备', hue: 260 };
}

export interface MarketClock {
  key: string;
  name: string;
  /** HH:MM（当地时区） */
  time: string;
  open: boolean;
}

interface MarketDef {
  key: string;
  name: string;
  tz: string;
  /** [开市HH:MM, 收市HH:MM] 当地时间，整分边界含头含尾 */
  openFrom: [number, number];
  openTo: [number, number];
}

const MARKETS: MarketDef[] = [
  { key: 'sh', name: '上海 · A股', tz: 'Asia/Shanghai', openFrom: [9, 30], openTo: [15, 0] },
  { key: 'jp', name: '东京', tz: 'Asia/Tokyo', openFrom: [9, 0], openTo: [15, 0] },
  { key: 'uk', name: '伦敦', tz: 'Europe/London', openFrom: [8, 0], openTo: [16, 30] },
  { key: 'us', name: '纽约', tz: 'America/New_York', openFrom: [9, 30], openTo: [16, 0] },
];

function localParts(now: Date, tz: string): { hh: number; mm: number; weekday: string } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    hour: '2-digit',
    minute: '2-digit',
    weekday: 'short',
    hour12: false,
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  let hh = Number(get('hour'));
  if (hh === 24) hh = 0; // 部分 ICU 以 24 表示午夜
  return { hh, mm: Number(get('minute')), weekday: get('weekday') };
}

export function getMarketClocks(now: Date = new Date()): MarketClock[] {
  return MARKETS.map((m) => {
    const { hh, mm, weekday } = localParts(now, m.tz);
    const t = hh * 60 + mm;
    const from = m.openFrom[0] * 60 + m.openFrom[1];
    const to = m.openTo[0] * 60 + m.openTo[1];
    const isWeekend = weekday === 'Sat' || weekday === 'Sun';
    const inSession = t >= from && t <= to;
    return {
      key: m.key,
      name: m.name,
      time: `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`,
      open: !isWeekend && inSession,
    };
  });
}
