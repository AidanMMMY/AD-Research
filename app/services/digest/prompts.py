"""Daily Digest LLM prompt 模板（2026-08-03，B3）。

公共 system prompt + 6 章节模板。设计要点：

- 分章节生成（而非单次长 prompt）：单次 3000-5000 字中文接近模型
  输出上限、任一失败全损、篇幅配比难控。6 次独立调用 + 1 次摘要，
  单节失败只降级该节。
- 第 2 节起 user prompt 附前节各 100 字摘要，保住跨节连贯
  （同一事件不在多节重复铺陈）。
- 纯 markdown 输出，不引入 JSON 解析失败面；章节标题固定为
  ``## <序号>、<标题>``，落库前校验 6 个 ``##`` 齐全。
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_PROMPT = """你是一位资深宏观与多资产策略分析师，为个人投资者撰写每日晨会综合研报。

写作要求：
1. 全文使用简体中文，机构晨会纪要风格：结论先行、段落紧凑、少用套话。
2. 覆盖行情（A股/美股/加密）、资讯、政策与宏观，允许发散联想（政治、历史、跨市场传导），但必须明确区分「事实」与「推测」——推测性判断用"笔者认为/可能/需观察"等措辞标注。
3. 严禁编造数据窗口之外的事实；所有数字必须来自随附的事实清单，引用时保留关键数字（涨跌幅、金额、评分）。
4. 事实清单中标注"数据缺失"的部分，如实一句话带过，不得虚构填充。
5. 加密资产部分保持简报级（1-2 句即可），不展开。
6. 【因果传导人话解释】涉及"某因素（政策/数据/事件/地缘等）将影响市场"的判断时，必须紧随其后用 1-3 句大白话拆解因果传导链条（A→B→C 的中间环节），并顺带解释链路上普通读者可能不懂的机制/术语（例如"降息为什么利好成长股""美债收益率上行为什么压制估值"这类机制要用一两句话说透）。禁止只抛结论不给逻辑——目标读者懂投资但不是宏观专家。
7. 直接输出章节正文 markdown（不要重复输出章节标题，标题由系统拼装）；可使用要点列表，但不要输出代码块。"""


@dataclass(frozen=True)
class SectionSpec:
    """单章节模板。"""

    key: str  # 机器标识（sections_json / degraded 用）
    title: str  # 中文标题（## 后文本，含序号）
    word_range: tuple[int, int]  # 目标字数区间
    facts_keys: tuple[str, ...]  # 该节使用哪些数据包的 facts
    instruction: str  # 章节任务说明


SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        key="overnight_news",
        title="一、隔夜全球要闻",
        word_range=(500, 700),
        facts_keys=("news",),
        instruction=(
            "梳理数据窗口内的全球重要资讯。按事件分桶（央行/监管/地缘/贸易/"
            "制裁等）组织，点明每条要闻的潜在市场含义——涉及影响判断时用"
            "大白话说清传导链条（为什么 A 会导致 B）；重要性低的归并简写。"
        ),
    ),
    SectionSpec(
        key="macro_policy",
        title="二、宏观、政策与央行",
        word_range=(500, 700),
        facts_keys=("macro", "news"),
        instruction=(
            "结合宏观指标快照与窗口内政策/央行类资讯，解读利率、通胀、汇率、"
            "流动性方向的最新变化；指标变化要引用具体数值与日期。政策传导"
            "到市场的机制（如降息如何利好成长股、收益率上行如何压制估值）"
            "必须用一两句人话解释清楚。"
        ),
    ),
    SectionSpec(
        key="market_recap",
        title="三、三市场行情复盘（A股 / 美股 / 加密）",
        word_range=(500, 700),
        facts_keys=("scores", "fund_flow", "news"),
        instruction=(
            "复盘 A股、美股、加密三个市场在窗口内的表现。A股结合大盘与板块"
            "资金流；美股结合评分榜与资讯面；加密简报级一两句带过。"
            "评分榜前列标的就是资金与动量的落点，挑 2-3 只点评——涨跌背后"
            "的驱动因素要讲清因果链（资金为什么流入/流出），不只报数字。"
        ),
    ),
    SectionSpec(
        key="sector_rotation",
        title="四、板块与主题轮动",
        word_range=(400, 600),
        facts_keys=("sector", "fund_flow"),
        instruction=(
            "解读板块轮动信号与 1 月回报 Top/Bottom 板块：哪些板块动量增强/"
            "减弱，与板块主力净流入是否互相印证，给出 1-2 个值得跟踪的主题方向。"
        ),
    ),
    SectionSpec(
        key="watchlist_lens",
        title="五、自选与组合透视",
        word_range=(800, 1200),
        facts_keys=("watchlist", "sentiment", "news"),
        instruction=(
            "这是全篇重点，篇幅最长。逐一分析主用户自选与持仓标的：最新行情"
            "与涨跌、窗口内相关新闻、最新评分与排名、近 3 日舆情情绪；持仓"
            "标的结合成本与浮盈亏点评。最后给出组合层面的整体观察（集中度、"
            "风格暴露、需要警惕的共振风险）。"
        ),
    ),
    SectionSpec(
        key="outlook_risks",
        title="六、今日关注与风险提示",
        word_range=(400, 600),
        facts_keys=("sellside", "news", "sector"),
        instruction=(
            "综合卖方研报观点与前述各节，列出今日（及本周）需要关注的事件、"
            "数据发布与标的催化；随后给出风险提示——包括数据缺口（若有 "
            "degraded 数据包需声明）与逻辑链条中最脆弱的环节。"
        ),
    ),
)

# 第 7 次调用：全篇摘要（Dashboard 摘要卡 / 邮件与 TG 首条用）
SUMMARY_INSTRUCTION = (
    "基于以下今日研报全文，写一段不超过 200 字的摘要：开门见山给出今日"
    "最重要的 1-2 个结论，随后一句带过市场状态与组合要点。只输出摘要"
    "正文，不要标题、不要列表。"
)

# 单节最终失败时的降级占位段（整体仍出报，前端以 partial 徽章提示）
SECTION_FALLBACK_TEXT = "（本节因数据/模型原因暂缺，请稍后在平台查看完整数据。）"


def build_section_user_prompt(
    spec: SectionSpec,
    facts: dict[str, str],
    degraded: list[str],
    prev_summaries: list[tuple[str, str]],
    window_text: str,
) -> str:
    """拼装单章节的 user prompt。

    Args:
        spec: 章节模板。
        facts: 各数据包的事实清单文本（DigestContext.facts）。
        degraded: 采集失败的数据包名（如实声明，防虚构）。
        prev_summaries: 前序章节 (标题, 100 字摘要)，第 2 节起非空。
        window_text: 人类可读的窗口描述。
    """
    parts = [f"数据窗口：{window_text}\n"]
    if degraded:
        parts.append(
            "注意：以下数据包采集失败、内容缺失，相关部分请如实一句话带过："
            + "、".join(degraded)
            + "\n"
        )
    parts.append("【事实清单】")
    for key in spec.facts_keys:
        text = facts.get(key)
        if text:
            parts.append(f"◆ {key} 数据包：\n{text}")
        else:
            parts.append(f"◆ {key} 数据包：（数据缺失）")
    if prev_summaries:
        parts.append("\n【前序章节摘要（保持连贯、避免重复铺陈）】")
        for title, brief in prev_summaries:
            parts.append(f"- {title}：{brief}")
    lo, hi = spec.word_range
    parts.append(
        f"\n【本节任务】{spec.title}（{lo}-{hi} 字）：{spec.instruction}"
    )
    return "\n".join(parts)


def build_summary_user_prompt(content_md: str) -> str:
    """拼装全篇摘要（第 7 次调用）的 user prompt。"""
    return f"{SUMMARY_INSTRUCTION}\n\n【研报全文】\n{content_md}"
