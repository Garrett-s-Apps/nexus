"""Tests for NEXUS Slack listener — pure function tests for md_to_slack and format_code_output."""

from src.slack.listener import md_to_slack, format_code_output


class TestMdToSlackBold:
    def test_md_to_slack_bold(self):
        """**bold** markdown should become *bold* Slack mrkdwn."""
        assert "*hello*" in md_to_slack("**hello**")

    def test_md_to_slack_bold_underscore(self):
        """__bold__ markdown should become *bold* Slack mrkdwn."""
        assert "*bold*" in md_to_slack("__bold__")


class TestMdToSlackHeaders:
    def test_md_to_slack_headers(self):
        """Markdown headers should become bold text in Slack."""
        result = md_to_slack("# Main Title")
        assert "*Main Title*" in result

    def test_md_to_slack_h2(self):
        """H2 headers should also become bold."""
        result = md_to_slack("## Section")
        assert "*Section*" in result

    def test_md_to_slack_h3(self):
        """H3 headers should also become bold."""
        result = md_to_slack("### Subsection")
        assert "*Subsection*" in result


class TestMdToSlackCodeBlocks:
    def test_md_to_slack_code_blocks(self):
        """Code blocks should be preserved in Slack format."""
        input_text = "```python\nprint('hello')\n```"
        result = md_to_slack(input_text)
        assert "```" in result
        assert "print('hello')" in result

    def test_md_to_slack_inline_code(self):
        """Inline code should be preserved as `code`."""
        result = md_to_slack("Use the `print` function")
        assert "`print`" in result


class TestMdToSlackLinks:
    def test_md_to_slack_links(self):
        """Markdown links should convert to Slack <url|text> format."""
        result = md_to_slack("[Click here](https://example.com)")
        assert "<https://example.com|Click here>" in result

    def test_md_to_slack_multiple_links(self):
        """Multiple links in one message should all convert."""
        text = "[A](https://a.com) and [B](https://b.com)"
        result = md_to_slack(text)
        assert "<https://a.com|A>" in result
        assert "<https://b.com|B>" in result


class TestMdToSlackLists:
    def test_md_to_slack_unordered_lists(self):
        """Unordered list items should become bullet points."""
        result = md_to_slack("- Item 1\n- Item 2\n- Item 3")
        lines = result.strip().split("\n")
        for line in lines:
            assert line.startswith("•")

    def test_md_to_slack_numbered_lists(self):
        """Numbered lists should also become bullet points."""
        result = md_to_slack("1. First\n2. Second\n3. Third")
        lines = result.strip().split("\n")
        for line in lines:
            assert line.startswith("•")

    def test_md_to_slack_asterisk_lists(self):
        """Asterisk lists should become bullet points."""
        result = md_to_slack("* Alpha\n* Beta")
        assert "•" in result


class TestMdToSlackHtmlEntities:
    def test_md_to_slack_html_entities(self):
        """HTML entities should be decoded."""
        assert "&" in md_to_slack("&amp;")
        assert "<" in md_to_slack("&lt;")
        assert ">" in md_to_slack("&gt;")
        assert '"' in md_to_slack("&quot;")
        assert "'" in md_to_slack("&#39;")

    def test_md_to_slack_nbsp(self):
        """Non-breaking space entity should become a regular space."""
        result = md_to_slack("hello&nbsp;world")
        assert "hello world" in result

    def test_md_to_slack_horizontal_rules(self):
        """Horizontal rules (---) should convert to em dashes."""
        result = md_to_slack("---")
        assert "———" in result


class TestFormatCodeOutput:
    def test_format_code_output_basic(self):
        """Basic text should produce section blocks."""
        blocks = format_code_output("Hello world")
        assert len(blocks) > 0
        assert blocks[0]["type"] == "section"
        assert "Hello world" in blocks[0]["text"]["text"]

    def test_format_code_output_with_agent_name(self):
        """Providing agent_name should add a context block as header."""
        blocks = format_code_output("Done!", agent_name="Derek")
        assert blocks[0]["type"] == "context"
        assert "Derek" in blocks[0]["elements"][0]["text"]

    def test_format_code_output_with_code(self):
        """Output with code blocks should create separate code sections."""
        output = "Here is the code:\n```python\ndef hello():\n    pass\n```\nEnd."
        blocks = format_code_output(output)
        # Should have at least a text block, a code block, and closing text
        has_code = any("```" in b.get("text", {}).get("text", "") for b in blocks)
        assert has_code

    def test_format_code_output_truncation(self):
        """Very long code should be truncated."""
        long_code = "```\n" + "x = 1\n" * 1000 + "```"
        blocks = format_code_output(long_code)
        for block in blocks:
            text = block.get("text", {}).get("text", "")
            # Slack block text limit is roughly 3000 chars; our code truncates at 2900
            assert len(text) <= 3100  # some overhead for formatting

    def test_format_code_output_empty(self):
        """Empty string should produce no blocks."""
        blocks = format_code_output("")
        assert blocks == []

    def test_format_code_output_only_code(self):
        """Code-only output should still produce blocks."""
        blocks = format_code_output("```\nprint('hi')\n```")
        assert len(blocks) > 0

    def test_format_code_output_multiple_code_blocks(self):
        """Multiple code blocks should each get their own section."""
        output = "First:\n```\ncode1\n```\nSecond:\n```\ncode2\n```"
        blocks = format_code_output(output)
        code_blocks = [b for b in blocks if "```" in b.get("text", {}).get("text", "")]
        assert len(code_blocks) >= 2
