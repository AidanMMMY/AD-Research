"""_strip_html / _strip_html_to_text 段落保留测试（2026-08-01 huxiu 段落粘连根治）。

两个函数分别在 rss_common（RSS 全文源 body）和 normalizer（body_html 兜底），
规则一致：块级标签边界 → \n\n，行内标签 → 空格，3+ 连续换行收敛为 \n\n。
"""

from app.services.news.normalizer import _strip_html_to_text
from app.services.news.sources.rss_common import _strip_html


class TestRssCommonStripHtml:
    def test_block_tags_become_paragraph_breaks(self):
        html = "<p>第一段。</p><p>第二段。</p><p>第三段。</p>"
        assert _strip_html(html) == "第一段。\n\n第二段。\n\n第三段。"

    def test_br_and_div_boundaries(self):
        html = "<div>甲<br>乙</div><div>丙</div>"
        assert _strip_html(html) == "甲\n乙\n\n丙"

    def test_inline_tags_do_not_create_breaks(self):
        html = "<p>这是<b>加粗</b>和<a href='x'>链接</a>文字。</p>"
        assert _strip_html(html) == "这是 加粗 和 链接 文字。"

    def test_excess_breaks_collapse_to_double_newline(self):
        html = "<p>一</p><br><br><br><p>二</p>"
        result = _strip_html(html)
        assert result == "一\n\n二"
        assert "\n\n\n" not in result

    def test_entities_still_unescaped(self):
        assert _strip_html("<p>a &amp; b&nbsp;c</p>") == "a & b c"

    def test_none_and_empty(self):
        assert _strip_html(None) is None
        assert _strip_html("") is None
        assert _strip_html("<p>  </p>") is None

    def test_huxiu_style_fulltext(self):
        """模拟虎嗅 RSS description：多 <p> 全文不得粘连成一段。"""
        html = "".join(f"<p>第{i}段内容，包含若干句子。</p>" for i in range(5))
        result = _strip_html(html)
        assert result is not None
        assert result.count("\n\n") == 4
        assert result.startswith("第0段")
        assert result.endswith("。")


class TestNormalizerStripHtmlToText:
    def test_block_tags_become_paragraph_breaks(self):
        html = "<p>alpha</p><p>beta</p>"
        assert _strip_html_to_text(html) == "alpha\n\nbeta"

    def test_heading_and_list_boundaries(self):
        html = "<h2>标题</h2><ul><li>甲</li><li>乙</li></ul>"
        assert _strip_html_to_text(html) == "标题\n\n甲\n\n乙"

    def test_excess_breaks_collapse(self):
        html = "<p>一</p></div></section><p>二</p>"
        result = _strip_html_to_text(html)
        assert "\n\n\n" not in result

    def test_none_and_empty(self):
        assert _strip_html_to_text(None) is None
        assert _strip_html_to_text("") is None

    def test_truncation_preserved(self):
        html = "<p>" + "长" * 9000 + "</p>"
        assert len(_strip_html_to_text(html)) == 8000
