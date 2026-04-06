import html
import json
import os
import re
import shutil
import urllib.parse


SOURCE_DIR = os.path.join(os.getcwd(), "mirror_httrack", "www.aspaklaria.info")
OUTPUT_DIR = os.path.join(os.getcwd(), "mobile_site")


HREF_RE = re.compile(r"<a\s+[^>]*href\s*=\s*(\".*?\"|'.*?'|[^\s>]+)", re.IGNORECASE)
HREF_ATTR_RE = re.compile(r"(<a\s+[^>]*href\s*=\s*)(\".*?\"|'.*?'|[^\s>]+)", re.IGNORECASE)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
SPAN_RE = re.compile(r"<span[^>]*>(.*?)</span>", re.IGNORECASE | re.DOTALL)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def extract_title(content, fallback):
    match = TITLE_RE.search(content)
    if not match:
        return fallback
    return html.unescape(match.group(1)).strip() or fallback


def extract_body(content):
    match = BODY_RE.search(content)
    if not match:
        return content
    return match.group(1).strip()


def extract_styles(content):
    return [m.group(1).strip() for m in STYLE_RE.finditer(content) if m.group(1).strip()]


def encode_path(path):
    normalized = urllib.parse.unquote(path)
    return urllib.parse.quote(normalized, safe="/%?=&:#.-_")


def output_path_for(rel_path):
    decoded_rel = urllib.parse.unquote(rel_path.replace(os.sep, "/"))
    return os.path.join(OUTPUT_DIR, decoded_rel.replace("/", os.sep))


def normalize_text(value):
    cleaned = re.sub(r"<[^>]+>", "", value)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_terms_from_index(index_path, index_rel):
    content = read_text(index_path)
    body = extract_body(content)
    terms = []
    base = index_rel.replace("\\", "/")
    if "/" in base:
        base = base.rsplit("/", 1)[0] + "/"
    else:
        base = ""

    for match in HREF_ATTR_RE.finditer(body):
        raw_href = match.group(2).strip("\"'")
        if not raw_href:
            continue
        lower = raw_href.lower()
        if ".htm" not in lower and ".html" not in lower:
            continue
        anchor_match = re.search(r">(.*?)</a>", body[match.start():match.start() + 300], re.IGNORECASE | re.DOTALL)
        if not anchor_match:
            continue
        term_text = normalize_text(anchor_match.group(1))
        if not term_text:
            continue
        resolved = urllib.parse.urljoin(base, html.unescape(raw_href))
        terms.append((term_text, encode_path(resolved)))
    return terms


def build_search_index(nav_items):
    entries = []
    seen = set()
    for item in nav_items:
        index_rel = item["raw"]
        source_path = os.path.join(SOURCE_DIR, index_rel.replace("/", os.sep))
        if not os.path.isfile(source_path):
            continue
        terms = extract_terms_from_index(source_path, index_rel)
        for term_text, href in terms:
            key = (href, term_text)
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "letter": item["text"],
                "term": term_text,
                "href": href
            })

    output_path = os.path.join(OUTPUT_DIR, "search-index.json")
    write_text(output_path, json.dumps(entries, ensure_ascii=False))


def normalize_body_links(body_html):
    def replacer(match):
        raw = match.group(2).strip("\"'")
        if not raw:
            return match.group(0)
        decoded = html.unescape(raw)
        lower = decoded.lower()
        if decoded.startswith("#"):
            return match.group(0)
        if lower.startswith(("http://", "https://", "mailto:", "tel:", "javascript:")):
            return match.group(0)
        if ".htm" not in lower and ".html" not in lower:
            return match.group(0)
        encoded = encode_path(decoded)
        return f"{match.group(1)}\"{encoded}\""

    return HREF_ATTR_RE.sub(replacer, body_html)


def extract_logo_text(logo_path):
    content = read_text(logo_path)
    spans = [html.unescape(s).strip() for s in SPAN_RE.findall(content)]
    spans = [s for s in spans if s]
    hebrew = spans[0] if spans else "אספקלריא"
    english = spans[1] if len(spans) > 1 else "ASPAKLARIA"
    return hebrew, english


def build_letter_nav(nav_path):
    content = read_text(nav_path)
    items = []
    for match in HREF_RE.finditer(content):
        raw = match.group(1).strip("\"'")
        if not raw:
            continue
        if not raw.lower().endswith(".htm") and not raw.lower().endswith(".html"):
            continue
        anchor_match = re.search(r">(.*?)</a>", content[match.start():match.start() + 200], re.IGNORECASE | re.DOTALL)
        text = html.unescape(anchor_match.group(1)).strip() if anchor_match else ""
        items.append({
            "raw": raw,
            "encoded": encode_path(raw),
            "text": text
        })
    return items


def relative_link(target, current_dir):
    target_path = os.path.join(OUTPUT_DIR, encode_path(target).replace("/", os.sep))
    return os.path.relpath(target_path, current_dir).replace(os.sep, "/")


def rel_prefix(path):
    parts = os.path.relpath(os.path.dirname(path), OUTPUT_DIR).split(os.sep)
    if parts == ["."]:
        return ""
    return "../" * len(parts)


def root_index_href(path):
    output_rel = rel_prefix(path)
    return output_rel + "../index.html"


def build_template(title, body_html, nav_items, logo_he, logo_en, css_path, home_href, body_class="", legacy_styles=None):
    nav_links = []
    for item in nav_items:
        nav_links.append(f'<a href="{item["encoded"]}">{item["text"]}</a>')
    nav_html = "\n".join(nav_links)

    legacy_block = ""
    if legacy_styles:
        legacy_css = "\n".join(legacy_styles)
        legacy_block = f"\n  <style>\n{legacy_css}\n  </style>"

    site_search_block = ""
    if "is-home" in body_class:
        site_search_block = """
    <div class=\"site-search\" data-role=\"site-search\" hidden>
      <label for=\"siteSearch\">חיפוש ישיר</label>
      <input id=\"siteSearch\" type=\"search\" placeholder=\"הקלד כדי לחפש ערך\" autocomplete=\"off\" list=\"termSuggestions\" />
      <datalist id=\"termSuggestions\"></datalist>
    </div>"""

    filter_block = ""
    if "is-home" not in body_class:
        filter_block = """
    <div class=\"term-filter\" data-role=\"term-filter\" hidden>
      <label for=\"termFilter\">חיפוש במונחים</label>
      <input id=\"termFilter\" type=\"search\" placeholder=\"הקלד כדי לסנן\" autocomplete=\"off\" />
    </div>"""

    return f"""<!doctype html>
<html lang=\"he\" dir=\"rtl\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <link rel=\"stylesheet\" href=\"{css_path}\" />{legacy_block}
</head>
<body class=\"site {body_class}\">
  <a class=\"skip\" href=\"#main\">דלג לתוכן</a>
  <header class=\"site__header\">
    <a class=\"brand\" href=\"{home_href}\" aria-label=\"עמוד ראשי\">
      <span class=\"brand__he\">{logo_he}</span>
      <span class=\"brand__en\">{logo_en}</span>
    </a>
    <nav class=\"letters\" aria-label=\"ניווט אותיות\">{nav_html}</nav>
  </header>
   <main id=\"main\" class=\"site__main\">
 {site_search_block}
 {filter_block}
    <div class=\"term-list\" data-role=\"term-list\">
{body_html}
    </div>
  </main>
  <footer class=\"site__footer\">
    <small>aspaklaria.info (mobile-friendly copy)</small>
  </footer>
  <script>
    (() => {{
      if (document.body.classList.contains('is-home')) {{
        const searchWrap = document.querySelector('[data-role="site-search"]');
        const input = document.getElementById('siteSearch');
        const datalist = document.getElementById('termSuggestions');
        if (searchWrap && input && datalist) {{
          fetch('search-index.json')
            .then((res) => res.json())
            .then((data) => {{
              const map = new Map();
              const fragment = document.createDocumentFragment();
              data.forEach((item) => {{
                const label = item.term + ' — ' + item.letter;
                if (!map.has(label)) {{
                  map.set(label, item.href);
                  const opt = document.createElement('option');
                  opt.value = label;
                  fragment.appendChild(opt);
                }}
                if (!map.has(item.term)) {{
                  map.set(item.term, item.href);
                }}
              }});
              datalist.appendChild(fragment);
              searchWrap.hidden = false;

              const go = () => {{
                const value = input.value.trim();
                if (!value) return;
                const target = map.get(value);
                if (target) window.location.href = target;
              }};

              input.addEventListener('change', go);
              input.addEventListener('keydown', (event) => {{
                if (event.key === 'Enter') go();
              }});
            }})
            .catch(() => {{}});
        }}
      }}

      const list = document.querySelector('[data-role="term-list"]');
      const filterWrap = document.querySelector('[data-role="term-filter"]');
      if (!list || !filterWrap) return;

      if (document.body.classList.contains('is-home')) return;

      const links = Array.from(list.querySelectorAll('a[href]'));
      if (links.length < 20) return;

      document.body.classList.add('is-index');
      filterWrap.hidden = false;

      const input = document.getElementById('termFilter');
      const items = links.map((link) => ({{
        link,
        text: link.textContent?.trim() || ''
      }}));

      const update = () => {{
        const query = (input.value || '').trim().toLowerCase();
        if (!query) {{
          items.forEach(({{ link }}) => {{
            const row = link.closest('p') || link;
            row.hidden = false;
          }});
          return;
        }}
        items.forEach(({{ link, text }}) => {{
          const row = link.closest('p') || link;
          row.hidden = !text.toLowerCase().includes(query);
        }});
      }};

      input.addEventListener('input', update);
    }})();
  </script>
</body>
</html>
"""


def copy_assets():
    for root, _dirs, files in os.walk(SOURCE_DIR):
        for name in files:
            lower = name.lower()
            if lower.endswith((".htm", ".html")):
                continue
            if lower.endswith((".htm.z", ".html.z", ".tmp", ".bak")):
                continue
            source_path = os.path.join(root, name)
            rel_path = os.path.relpath(source_path, SOURCE_DIR)
            dest_path = output_path_for(rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source_path, dest_path)


def main():
    if not os.path.isdir(SOURCE_DIR):
        raise SystemExit("mirror_raw directory not found")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    logo_he, logo_en = extract_logo_text(os.path.join(SOURCE_DIR, "Logo_Aspaklaria_V25.html"))
    nav_items = build_letter_nav(os.path.join(SOURCE_DIR, "AlepBet_Title_V25.html"))

    copy_assets()

    home_source = os.path.join(SOURCE_DIR, "Aspaklaria_main_V20.html")
    home_body = ""
    home_title = "Aspaklaria"
    home_path = os.path.join(OUTPUT_DIR, "index.html")
    home_css = rel_prefix(home_path) + "site.css"
    home_href = root_index_href(home_path)
    home_nav = [{
        "raw": item["raw"],
        "encoded": relative_link(item["encoded"], os.path.dirname(home_path)),
        "text": item["text"]
    } for item in nav_items]
    home_html = build_template(home_title, home_body, home_nav, logo_he, logo_en, home_css, home_href, "is-home")
    write_text(home_path, home_html)

    build_search_index(nav_items)

    for root, _dirs, files in os.walk(SOURCE_DIR):
        for name in files:
            if not name.lower().endswith((".htm", ".html")):
                continue
            if name.lower().endswith((".z.htm", ".z.html")):
                continue
            source_path = os.path.join(root, name)
            rel_path = os.path.relpath(source_path, SOURCE_DIR)
            if rel_path in ("index.html", "AlepBet_Title_V25.html", "Logo_Aspaklaria_V25.html", "Aspaklaria_main_V20.html"):
                continue
            dest_path = output_path_for(rel_path)
            content = read_text(source_path)
            body = normalize_body_links(extract_body(content))
            title = extract_title(content, "Aspaklaria")
            legacy_styles = extract_styles(content)
            css_path = rel_prefix(dest_path) + "site.css"
            current_dir = os.path.dirname(dest_path)
            page_nav = [{
                "raw": item["raw"],
                "encoded": relative_link(item["encoded"], current_dir),
                "text": item["text"]
            } for item in nav_items]
            home_href = root_index_href(dest_path)
            html_page = build_template(title, body, page_nav, logo_he, logo_en, css_path, home_href, "", legacy_styles)
            write_text(dest_path, html_page)


if __name__ == "__main__":
    main()
