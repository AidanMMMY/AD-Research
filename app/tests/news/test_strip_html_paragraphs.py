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


# ---------------------------------------------------------------------------
# 2026-08-02 cls 段落粘连根治：财联社/华尔街见闻 API 返回的 content/brief
# 是「纯文本 + \n\n 分段」（wallstreetcn 是 <p> HTML），crawler 层旧路径
# BaseCrawler.strip_html 用 \s+ 折叠把所有换行压成空格，正文粘成一段。
# 修复 = BaseCrawler.strip_html_preserve_paragraphs + cls/wallstreetcn 改走它。
# ---------------------------------------------------------------------------

import asyncio
import json

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.sources.cls import ClsCrawler
from app.services.news.sources.wallstreetcn import WallstreetcnCrawler


def _fake_response(text: str) -> _Response:
    return _Response(
        url="test://",
        text=text,
        content=text.encode("utf-8"),
        status_code=200,
    )


class TestBaseCrawlerStripHtmlPreserveParagraphs:
    def test_block_tags_become_paragraph_breaks(self):
        html = "<p>第一段。</p><p>第二段。</p>"
        assert BaseCrawler.strip_html_preserve_paragraphs(html) == "第一段。\n\n第二段。"

    def test_plain_text_newlines_survive(self):
        """cls API content 形态：无 HTML 标签、\n\n 分段——换行必须原样保留。"""
        text = "【标题】第一段内容。\n\n第二段内容。\n\n第三段内容。"
        assert BaseCrawler.strip_html_preserve_paragraphs(text) == text

    def test_br_becomes_single_newline(self):
        assert BaseCrawler.strip_html_preserve_paragraphs("甲<br>乙") == "甲\n乙"

    def test_excess_breaks_collapse(self):
        html = "<p>一</p><br><br><br><p>二</p>"
        result = BaseCrawler.strip_html_preserve_paragraphs(html)
        assert result == "一\n\n二"

    def test_empty(self):
        assert BaseCrawler.strip_html_preserve_paragraphs("") == ""

    def test_strip_html_still_single_line(self):
        """原 strip_html 语义不变（标题/brief 单行场景）。"""
        assert BaseCrawler.strip_html("<p>甲</p> <p>乙</p>") == "甲 乙"
        assert BaseCrawler.strip_html("甲\n\n乙") == "甲 乙"


class TestClsParagraphs:
    """真实形态的 cls telegraph payload：content/brief 是纯文本 \\n\\n 分段。"""

    _PAYLOAD = json.dumps(
        {
            "errno": 0,
            "data": {
                "roll_data": [
                    {
                        "id": 2443149,
                        "type": -1,
                        "title": "周六你需要知道的隔夜全球要闻",
                        "brief": "【周六你需要知道的隔夜全球要闻】 1、美股三大指数集体收涨。\n\n2、据报道，美联储主席沃什考虑减少政策会议频率。\n\n3、美国官员表示，特朗普已下令对伊朗发动新一轮袭击。",
                        "content": "【周六你需要知道的隔夜全球要闻】 1、美股三大指数集体收涨。\n\n2、据报道，美联储主席沃什考虑减少政策会议频率。\n\n3、美国官员表示，特朗普已下令对伊朗发动新一轮袭击。",
                        "ctime": "1753108800",
                    },
                    {
                        "id": 2443150,
                        "type": -1,
                        "title": "",
                        "brief": "【无标题快讯】第一段。\n\n第二段。",
                        "content": "",
                        "ctime": "1753108860",
                    },
                ]
            },
        },
        ensure_ascii=False,
    )

    def test_body_preserves_paragraph_breaks(self):
        crawler = ClsCrawler()
        articles = asyncio.run(crawler.parse(_fake_response(self._PAYLOAD)))
        assert len(articles) == 2
        body = articles[0].body
        assert body is not None
        assert body.count("\n\n") == 2
        assert "1、美股" in body and "3、美国官员" in body

    def test_fallback_title_is_single_line(self):
        """brief 现在保留换行，标题兜底必须先折叠空白——标题不得含 \\n。"""
        crawler = ClsCrawler()
        articles = asyncio.run(crawler.parse(_fake_response(self._PAYLOAD)))
        title = articles[1].title
        assert "\n" not in title
        assert title.startswith("【无标题快讯】第一段。")


class TestWallstreetcnParagraphs:
    def _payload(self, **item_overrides) -> str:
        item = {
            "id": 3143600,
            "title": "早餐FM-Radio",
            "content_text": "",
            "content": "<p>第一段。</p>\n<p>第二段。</p>\n<p>第三段。</p>\n",
            "display_time": 1753108800,
            "uri": "https://wallstreetcn.com/livenews/3143600",
        }
        item.update(item_overrides)
        return json.dumps({"data": {"items": [item]}}, ensure_ascii=False)

    def test_html_fallback_preserves_paragraphs(self):
        """content_text 缺失时回退剥 content HTML——<p> 边界必须变 \\n\\n。"""
        crawler = WallstreetcnCrawler()
        articles = crawler._parse_payload(self._payload())
        assert len(articles) == 1
        assert articles[0].body == "第一段。\n\n第二段。\n\n第三段。"

    def test_content_text_newlines_pass_through(self):
        """API content_text 自带 \\n\\n（已验证线上形态）——不得再折叠。"""
        text = "拉脱维亚公告。\n\n公告说，口岸因技术故障暂停通关。"
        crawler = WallstreetcnCrawler()
        articles = crawler._parse_payload(self._payload(content_text=text, content=""))
        assert articles[0].body == text
