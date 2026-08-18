"""MiniMax provider think 块剥除回归测试（2026-08-18）。

事故：MiniMax 推理模型把 <think>思维链</think> 混在正文返回，每日研报
35k 字里一半是 think 原文直接发布到站内+邮件。修复在 provider 出口
统一剥除（complete/chat 两路径）。
"""

from app.services.llm.minimax_provider import _strip_think


class TestStripThink:
    def test_no_think_passthrough(self):
        assert _strip_think("正常正文内容") == "正常正文内容"

    def test_empty(self):
        assert _strip_think("") == ""

    def test_single_block(self):
        text = "<think>让我想想……</think>正式回答"
        assert _strip_think(text) == "正式回答"

    def test_multiple_blocks(self):
        text = "<think>第一段推理</think>正文一<think>第二段推理</think>正文二"
        assert _strip_think(text) == "正文一正文二"

    def test_multiline_block(self):
        text = "<think>\n多行\n推理\n</think>\n## 章节标题\n正文"
        assert _strip_think(text) == "## 章节标题\n正文"

    def test_unclosed_block_stripped_to_end(self):
        text = "正文开头<think>推理被截断再也没闭合"
        assert _strip_think(text) == "正文开头"

    def test_think_only_returns_empty(self):
        # 整块只有 think → 空串，调用方走"空输出=失败/降级"既有路径
        assert _strip_think("<think>只有推理没有正文</think>") == ""

    def test_case_insensitive(self):
        assert _strip_think("<THINK>大写标签</THINK>正文") == "正文"
