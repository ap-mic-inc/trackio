import { describe, expect, it } from "vitest";
import { renderMarkdown, safeUrl } from "./markdown.js";

describe("renderMarkdown", () => {
  it("renders the showcase report with its table and list", () => {
    const html = renderMarkdown(
      "# Showcase 報告\n\n| Metric | Value |\n| --- | --- |\n| Steps | 40 |\n| Final loss | ~0.078 |\n\n- 圖片每 5 步一次\n- Trace 每 4 步一次\n- 兩個 histogram：`weights/layer0`、`grads/layer0`\n",
    );
    expect(html).toBe(
      "<h2>Showcase 報告</h2>" +
        '<div class="md-table"><table><thead><tr><th>Metric</th><th>Value</th></tr></thead>' +
        "<tbody><tr><td>Steps</td><td>40</td></tr><tr><td>Final loss</td><td>~0.078</td></tr></tbody></table></div>" +
        "<ul><li>圖片每 5 步一次</li><li>Trace 每 4 步一次</li>" +
        "<li>兩個 histogram：<code>weights/layer0</code>、<code>grads/layer0</code></li></ul>",
    );
  });

  it("aligns table columns, pads short rows, and allows escaped pipes", () => {
    const html = renderMarkdown("a | b | c\n:-- | :-: | --:\n1 | x \\| y\n");
    expect(html).toContain('<th style="text-align: left">a</th>');
    expect(html).toContain('<th style="text-align: center">b</th>');
    expect(html).toContain('<td style="text-align: center">x | y</td>');
    expect(html).toContain('<td style="text-align: right"></td>');
  });

  it("formats inline markup", () => {
    expect(renderMarkdown("**bold** *em* _em2_ ~~gone~~ `a*b*c`")).toBe(
      "<p><strong>bold</strong> <em>em</em> <em>em2</em> <del>gone</del> <code>a*b*c</code></p>",
    );
    expect(renderMarkdown("snake_case_name and 2*3*4")).toBe(
      "<p>snake_case_name and 2*3*4</p>",
    );
  });

  it("renders links with safe targets only", () => {
    expect(renderMarkdown("[docs](https://example.com/a?b=1&c=2)")).toBe(
      '<p><a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">docs</a></p>',
    );
    expect(renderMarkdown("[x](javascript:alert(1))")).not.toContain("<a ");
    expect(safeUrl("data:text/html,x")).toBeNull();
    expect(safeUrl("./runs/1")).toBe("./runs/1");
  });

  it("escapes raw HTML everywhere", () => {
    const html = renderMarkdown(
      '<img src=x onerror=alert(1)>\n\n| <b>h</b> |\n| - |\n| <script>x</script> |\n\n- <i>li</i>\n\n```\n<script>\n```',
    );
    expect(html).not.toMatch(/<(img|script|b|i)[ >]/);
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).toContain("&lt;script&gt;x&lt;/script&gt;");
  });

  it("renders ordered and nested lists", () => {
    expect(renderMarkdown("3. three\n4. four\n   - nested\n5. five")).toBe(
      '<ol start="3"><li>three</li><li>four<ul><li>nested</li></ul></li><li>five</li></ol>',
    );
  });

  it("renders fenced code, quotes, rules, and paragraph breaks", () => {
    expect(renderMarkdown("```python\nx = 1 * 2 * 3\n```")).toBe(
      '<pre><code class="language-python">x = 1 * 2 * 3</code></pre>',
    );
    expect(renderMarkdown("> quoted **text**")).toBe(
      "<blockquote><p>quoted <strong>text</strong></p></blockquote>",
    );
    expect(renderMarkdown("above\n\n---\n\nbelow")).toBe("<p>above</p><hr><p>below</p>");
    expect(renderMarkdown("line one\nline two")).toBe("<p>line one<br>line two</p>");
  });

  it("shifts headings below the card title", () => {
    expect(renderMarkdown("# a\n## b\n###### f")).toBe("<h2>a</h2><h3>b</h3><h6>f</h6>");
  });
});
