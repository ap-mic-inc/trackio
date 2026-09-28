// Minimal GitHub-flavored Markdown renderer for logged reports.
//
// All text is HTML-escaped before any markup is generated, so the output only
// contains tags this module emits; link targets are limited to http(s),
// mailto, and relative URLs. Headings are shifted down one level because
// reports render inside a card that already has a title.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

export function safeUrl(url) {
  const trimmed = String(url).trim();
  if (/^(https?:|mailto:)/i.test(trimmed)) return trimmed;
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return null;
  return trimmed;
}

function renderInline(text) {
  const codes = [];
  let out = String(text).replace(/(`+)([\s\S]*?[^`])\1(?!`)/g, (_, _ticks, code) => {
    codes.push(`<code>${escapeHtml(code.trim())}</code>`);
    return `\uE000${codes.length - 1}\uE000`;
  });
  const links = [];
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (match, label, url) => {
    const href = safeUrl(url);
    if (href === null) return match;
    links.push({ label, href });
    return `\uE001${links.length - 1}\uE001`;
  });
  out = escapeHtml(out);
  out = out
    .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>")
    .replace(/__(?=\S)([\s\S]*?\S)__/g, "<strong>$1</strong>")
    .replace(/~~(?=\S)([\s\S]*?\S)~~/g, "<del>$1</del>")
    .replace(/(^|[^*\w])\*(?=\S)([^*]*?\S)\*(?![*\w])/g, "$1<em>$2</em>")
    .replace(/(^|[^_\w])_(?=\S)([^_]*?\S)_(?![_\w])/g, "$1<em>$2</em>");
  out = out.replace(/\uE001(\d+)\uE001/g, (_, i) => {
    const { label, href } = links[Number(i)];
    return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${renderInline(label)}</a>`;
  });
  return out.replace(/\uE000(\d+)\uE000/g, (_, i) => codes[Number(i)]);
}

const FENCE = /^\s{0,3}(```+|~~~+)\s*([\w+-]*)\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const LIST_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const TABLE_SEPARATOR = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

function splitRow(line) {
  let row = line.trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
  const cells = [];
  let current = "";
  for (let i = 0; i < row.length; i++) {
    if (row[i] === "\\" && row[i + 1] === "|") {
      current += "|";
      i++;
    } else if (row[i] === "|") {
      cells.push(current.trim());
      current = "";
    } else {
      current += row[i];
    }
  }
  cells.push(current.trim());
  return cells;
}

function isTableStart(lines, i) {
  return (
    lines[i].includes("|") &&
    i + 1 < lines.length &&
    lines[i + 1].includes("-") &&
    TABLE_SEPARATOR.test(lines[i + 1])
  );
}

function renderTable(lines, start) {
  const header = splitRow(lines[start]);
  const aligns = splitRow(lines[start + 1]).map((cell) => {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    if (left) return "left";
    return null;
  });
  const cell = (tag, text, col) => {
    const align = aligns[col] ? ` style="text-align: ${aligns[col]}"` : "";
    return `<${tag}${align}>${renderInline(text)}</${tag}>`;
  };
  let i = start + 2;
  const rows = [];
  while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
    const cells = splitRow(lines[i]);
    rows.push(
      `<tr>${header.map((_, col) => cell("td", cells[col] ?? "", col)).join("")}</tr>`,
    );
    i++;
  }
  const head = `<tr>${header.map((text, col) => cell("th", text, col)).join("")}</tr>`;
  const body = rows.length ? `<tbody>${rows.join("")}</tbody>` : "";
  return { html: `<div class="md-table"><table><thead>${head}</thead>${body}</table></div>`, next: i };
}

function renderList(lines, start) {
  const first = LIST_ITEM.exec(lines[start]);
  const indent = first[1].length;
  const ordered = /\d/.test(first[2]);
  const startNumber = ordered ? parseInt(first[2], 10) : 1;
  const items = [];
  let i = start;
  while (i < lines.length) {
    const match = LIST_ITEM.exec(lines[i]);
    if (!match || match[1].length !== indent || /\d/.test(match[2]) !== ordered) break;
    const body = [match[3]];
    i++;
    while (i < lines.length && lines[i].trim()) {
      const nested = LIST_ITEM.exec(lines[i]);
      if (nested && nested[1].length <= indent) break;
      body.push(lines[i].slice(Math.min(indent + 2, lines[i].search(/\S|$/))));
      i++;
    }
    const [text, ...rest] = body;
    const nestedHtml = rest.length ? renderBlocks(rest) : "";
    items.push(`<li>${renderInline(text)}${nestedHtml}</li>`);
    if (i < lines.length && !lines[i].trim()) {
      const after = lines.slice(i).findIndex((line) => line.trim());
      const next = after === -1 ? null : LIST_ITEM.exec(lines[i + after]);
      if (next && next[1].length === indent && /\d/.test(next[2]) === ordered) {
        i += after;
      }
    }
  }
  const tag = ordered ? "ol" : "ul";
  const startAttr = ordered && startNumber !== 1 ? ` start="${startNumber}"` : "";
  return { html: `<${tag}${startAttr}>${items.join("")}</${tag}>`, next: i };
}

function startsBlock(lines, i) {
  const line = lines[i];
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    RULE.test(line) ||
    QUOTE.test(line) ||
    LIST_ITEM.test(line) ||
    isTableStart(lines, i)
  );
}

function renderBlocks(lines) {
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = FENCE.exec(line);
    if (fence) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) {
        code.push(lines[i]);
        i++;
      }
      i++;
      const lang = fence[2] ? ` class="language-${escapeHtml(fence[2])}"` : "";
      out.push(`<pre><code${lang}>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i++;
      continue;
    }
    if (RULE.test(line)) {
      out.push("<hr>");
      i++;
      continue;
    }
    if (QUOTE.test(line)) {
      const quoted = [];
      while (i < lines.length && QUOTE.test(lines[i])) {
        quoted.push(QUOTE.exec(lines[i])[1]);
        i++;
      }
      out.push(`<blockquote>${renderBlocks(quoted)}</blockquote>`);
      continue;
    }
    if (isTableStart(lines, i)) {
      const table = renderTable(lines, i);
      out.push(table.html);
      i = table.next;
      continue;
    }
    if (LIST_ITEM.test(line)) {
      const list = renderList(lines, i);
      out.push(list.html);
      i = list.next;
      continue;
    }
    const paragraph = [line.trim()];
    i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) {
      paragraph.push(lines[i].trim());
      i++;
    }
    out.push(`<p>${paragraph.map(renderInline).join("<br>")}</p>`);
  }
  return out.join("");
}

export function renderMarkdown(markdown) {
  if (!markdown) return "";
  return renderBlocks(String(markdown).replace(/\r\n?/g, "\n").split("\n"));
}
