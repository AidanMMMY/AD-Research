"""繁体中文 → 简体中文转换（OpenCC t2s）。

平台 2026-07 起接入了大量台湾 / 香港中文源（科技新报 zhb_technews、
iThome 台湾 zhb_ithometw、動區動趨 zhb_blocktempo、端传媒、台湾播客
shownotes zhx_* 等），正文是繁体中文；产品要求一律以简体中文展示。

设计要点
--------
* **入库时转换，不在读路径 / 前端转换**：列表页性能和多端一致性。
  转换点只有两处 —— ``NewsNormalizer.normalize``（新文章入库）和
  ``ContentFetcher.fetch``（全文补抓回填 ``full_content``），覆盖
  所有 ``news_article`` 写入路径。
* **语言门控 + 繁体特征检测双重保护**：只对 ``language`` 为中文变体
  （``zh`` / ``zh-tw`` / ``zh-hant`` …，复用
  ``translation_service.is_chinese_language``）的文章做转换，且仅当
  文本检出繁体专属字时才真正调用 OpenCC。日文 / 韩文源不会误转
  （日文中虽有与繁体同形的汉字，但语言门控已排除）。
* **OpenCC t2s 对已是简体的文本基本幂等**，所以即便检测误报
  （简体文章里引用了「臺北」等专名），转换结果也无害。
* **HTML 安全**：OpenCC 只映射 CJK 字符，HTML 标签 / 属性均为 ASCII，
  直接对 ``body_html`` 整体转换不会破坏标签。

存量数据由 ``scripts/backfill_zh_traditional_to_simplified.py`` 幂等回填。
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# 高频「繁体专属」字符集：这些字在规范简体文本中不会出现（或其简体
# 对应字形不同）。命中任意一个即视为含繁体特征。刻意只收高频字，
# 避免把简体/繁体同形字（如「解」「台」「於」→ 於是繁体专属 ✓ 但
# 「解」两岸同形 ✗）混进来造成全量误判。
_TRADITIONAL_ONLY_CHARS: frozenset[str] = frozenset(
    "資訊臺灣這裡麼瞭軟體為們發現時間會來說對讀點學國後個過還進開關讓認實"
    "經準網頁瀏覽車馬門問聞長風飛見廣電腦機場記憶標於與並處線總結約題觀"
    "業務遊戲樂團買賣書數據庫無論種類係統計劃設營運產權價趨勢區塊鏈貨幣"
    "財報僅據稱導緻麽妳祂牠嚮"
)


@lru_cache(maxsize=1)
def _converter():
    """惰性构建 OpenCC t2s 转换器（进程级单例）。

    首次调用约几十 ms（加载字典），之后基本免费。放在 lru_cache
    里是为了让测试可以 monkeypatch 而不污染全局状态。
    """
    from opencc import OpenCC

    return OpenCC("t2s")


def has_traditional(text: str | None) -> bool:
    """检测文本是否含繁体专属字符。空 / None 返回 False。"""
    if not text:
        return False
    return any(ch in _TRADITIONAL_ONLY_CHARS for ch in text)


def to_simplified(text: str | None) -> str | None:
    """无条件繁→简转换；失败时返回原文（never raises）。"""
    if not text:
        return text
    try:
        return _converter().convert(text)
    except Exception as exc:  # noqa: BLE001 - 转换失败不能阻断入库
        logger.warning("zh_convert: OpenCC conversion failed: %s", exc)
        return text


def to_simplified_if_traditional(text: str | None) -> str | None:
    """检出繁体特征才转换；否则原样返回。"""
    if not text or not has_traditional(text):
        return text
    return to_simplified(text)


def convert_article_text_fields(
    fields: dict[str, str | None],
    *,
    language: str | None,
) -> dict[str, str | None]:
    """对一组文本字段做「中文文章 + 繁体特征」门控的原地转换。

    ``fields`` 形如 ``{"title": ..., "body": ..., "body_html": ...,
    "full_content": ...}``；非中文语言或已简体的字段原样保留。
    返回新 dict（不修改入参），方便调用方按需取用。
    """
    from app.services.news.translation_service import is_chinese_language

    if not is_chinese_language(language):
        return fields
    return {key: to_simplified_if_traditional(value) for key, value in fields.items()}
