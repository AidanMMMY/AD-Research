/**
 * Dashboard "今日一课" lightweight lesson bank.
 *
 * Curated, hand-written one-paragraph investment lessons surfaced on the
 * home page. The much larger termDictionary (200+ entries) powers the
 * HelpPopover / 学习术语 pages; the lesson bank is intentionally short
 * and conversational so the dashboard card stays readable.
 *
 * Each entry has:
 *   - id: stable string key (used for dedup / "no-repeat this session")
 *   - title: 1-line heading
 *   - body: 1-2 sentence conversational explanation
 *   - tip: optional 1-line actionable takeaway
 *   - tag: short category chip ("风险"/"估值"/"宏观"/"行为" ...)
 *
 * Adding more lessons: append to the array. The dashboard dedup is
 * length-aware, so 8-30 entries all play nicely.
 */

export interface LessonEntry {
  id: string;
  title: string;
  body: string;
  tip?: string;
  tag: '风险' | '估值' | '宏观' | '行为' | '组合' | '基本面' | '周期' | '量化';
}

export const LESSON_BANK: LessonEntry[] = [
  {
    id: 'risk-volatility',
    title: '波动 ≠ 风险',
    body:
      '波动率衡量的是价格上下跳动的幅度，但它并不等于本金永久损失的概率。一只 30% 年化波动的 ETF 长期持有的实际最大回撤，可能远低于另一只 15% 波动但回撤管理差的标的。',
    tip: '看最大回撤 (MDD) 和恢复天数，而不是只看 std-dev。',
    tag: '风险',
  },
  {
    id: 'sharpe-tradeoff',
    title: '夏普比率：每一单位风险换多少收益',
    body:
      '夏普比率 = (组合收益 - 无风险利率) / 组合波动率。数值越高代表"性价比"越好；但它假设收益是正态分布，对尾部风险不敏感，需要搭配 Sortino / 最大回撤一起看。',
    tip: '夏普 > 1 算优秀；> 2 罕见且多半伴随规模天花板。',
    tag: '风险',
  },
  {
    id: 'pe-context',
    title: 'PE 估值要看"分位"',
    body:
      '同一只 ETF 当前 PE = 30 听上去贵，但若过去十年 90% 时间都在 25-35 之间，那其实只是中位数偏上；反之 PE = 12 若位于历史 5% 分位以下，才是真正"便宜"。',
    tip: '比较 PE 的绝对值意义有限，看"过去 5-10 年分位数"更靠谱。',
    tag: '估值',
  },
  {
    id: 'dca-vs-timing',
    title: '定投本身就是择时策略',
    body:
      '定期定额意味着在低价时多买份额、高价时少买份额，长期下来会自动形成"低买高买"的复利效应。把定投和"择时"对立起来，是常见的认知误区。',
    tip: '坚持 3 年以上的纪律，比短期择时贡献的 alpha 大得多。',
    tag: '行为',
  },
  {
    id: 'correlation-decline',
    title: '低相关性是组合的免费午餐',
    body:
      '当两只 ETF 各自的年化波动都是 20% 时，如果它们完全负相关，组合波动可以降到 0；如果完全正相关，组合波动还是 20%。相关性是组合构建里唯一"白嫖"的多样化收益。',
    tip: '至少 3-5 个低相关资产类别（A 股 / 美股 / 债券 / 商品 / 海外），才有真正的分散效果。',
    tag: '组合',
  },
  {
    id: 'macro-policy-lag',
    title: '货币政策有 6-12 个月的滞后期',
    body:
      '美联储加息/降息从政策落地到实体经济反映出来通常需要 6-12 个月。市场预期会抢跑政策，所以"已知的利空"反而可能已经 priced in。',
    tip: '关注"实际利率 = 名义利率 - 通胀"，它对资产定价更直接。',
    tag: '宏观',
  },
  {
    id: 'reverse-investment',
    title: '逆向思考：人多的地方别去',
    body:
      '当一只 ETF 连续 3 个月霸榜热搜、身边从不炒股的人都在讨论时，往往已经进入"流动性最充裕、预期最乐观"的阶段——这恰恰是聪明钱开始减仓的时机。',
    tip: '设一个"反向指标"：当券商 APP 月活创新高 → 减仓 10-20%。',
    tag: '行为',
  },
  {
    id: 'fund-flow-leading',
    title: '资金流向是先行指标',
    body:
      'ETF 申赎数据反映了真实资金的去留，比价格更"诚实"。连续 20 日净申购 + 净值横盘，往往是机构在悄悄吸筹；连续净赎回 + 净值上涨，可能是诱多。',
    tip: '看 ETF 每日份额变化 × 净值，估算净流入金额。',
    tag: '基本面',
  },
  {
    id: 'cycle-mean-reversion',
    title: '万物皆周期，别线性外推',
    body:
      '美林时钟把经济划分为复苏、过热、滞胀、衰退四阶段，每个阶段的"最佳资产"完全不同。用过去 3 年的赢家去押未来 3 年，大概率踩错节奏。',
    tip: '每季度检查一次你的组合是否还匹配当前宏观阶段。',
    tag: '周期',
  },
  {
    id: 'position-sizing',
    title: '单笔仓位 ≤ 总资金的 5%',
    body:
      '凯利公式告诉你最优仓位，但实战中用 1/4 凯利更稳妥。即便你判断正确率高达 70%，单笔仓位也不应超过总资金的 5%，给"判断错了"留余地。',
    tip: '重仓 = 把策略收益和择时能力乘在了一起，两错一次满盘皆输。',
    tag: '风险',
  },
  {
    id: 'factor-crowding',
    title: '因子拥挤度是 alpha 的天花板',
    body:
      '小盘、质量、低波、动量……这些因子在量化圈都被广泛使用。当太多人拥挤在同一个因子上，因子溢价会迅速衰减，"低风险异常"过去 10 年已经从 +5%/年掉到接近 0。',
    tip: '关注因子相关性矩阵；当相关性普遍 > 0.6 时，说明市场进入"单因子"行情。',
    tag: '量化',
  },
  {
    id: 'profit-warning',
    title: '财报季警惕"惊喜陷阱"',
    body:
      '一只 ETF 底层持仓里某权重股业绩超预期，市场可能当天涨 3%，但如果管理层指引下调（forward guidance 走弱），接下来 3 个月反而可能跑输指数 10%+。',
    tip: '看 forward P/E 变化，而不是 trailing P/E；分析师一致预期的修订方向更重要。',
    tag: '基本面',
  },
];

/**
 * Pick a random lesson that is NOT in the "already shown this session"
 * set. Caller owns the set (typically a useRef). When the bank is
 * exhausted (everyone has been shown), starts over — by design,
 * because the user wants a fresh pick, not a fallback to a stale one.
 */
export function pickLesson(
  bank: LessonEntry[],
  exclude: ReadonlySet<string>,
): LessonEntry | null {
  if (bank.length === 0) return null;
  const pool = bank.filter((l) => !exclude.has(l.id));
  const source = pool.length > 0 ? pool : bank;
  return source[Math.floor(Math.random() * source.length)];
}