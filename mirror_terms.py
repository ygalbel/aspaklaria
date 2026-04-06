import html
import os
import re
import sys
import urllib.parse
import urllib.request


BASE_URL = "https://www.aspaklaria.info/"
BASE_DIR = os.path.join(os.getcwd(), "mirror_raw")


HREF_RE = re.compile(r"href\s*=\s*(\".*?\"|'.*?'|[^\s>]+)", re.IGNORECASE)


def iter_html_files(base_dir):
    for root, _dirs, files in os.walk(base_dir):
        for name in files:
            if name.lower().endswith(".htm") or name.lower().endswith(".html"):
                yield os.path.join(root, name)


def resolve_url(file_path, href):
    rel_dir = os.path.relpath(os.path.dirname(file_path), BASE_DIR)
    if rel_dir == ".":
        rel_dir = ""
    base = urllib.parse.urljoin(BASE_URL, rel_dir.replace(os.sep, "/") + "/")
    return urllib.parse.urljoin(base, href)


def normalize_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    if parts.netloc not in ("www.aspaklaria.info", "aspaklaria.info"):
        return None
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote_plus(parts.query, safe="=&%")
    return urllib.parse.urlunsplit((parts.scheme, "www.aspaklaria.info", path, query, parts.fragment))


def url_to_path(url):
    parts = urllib.parse.urlsplit(url)
    if not parts.path or parts.path.endswith("/"):
        return None
    return os.path.join(BASE_DIR, parts.path.lstrip("/"))


def collect_links():
    urls = set()
    for file_path in iter_html_files(BASE_DIR):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
        except OSError:
            continue
        for match in HREF_RE.finditer(content):
            raw = match.group(1).strip("\"'")
            if not raw:
                continue
            decoded = html.unescape(raw)
            if decoded.startswith("#"):
                continue
            if decoded.lower().startswith(("mailto:", "javascript:", "tel:")):
                continue
            if ".htm" not in decoded.lower():
                continue
            resolved = resolve_url(file_path, decoded)
            normalized = normalize_url(resolved)
            if normalized:
                urls.add(normalized)
    return urls


def download(url, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read()
    with open(dest_path, "wb") as handle:
        handle.write(content)


def parse_limit(argv):
    if len(argv) < 2:
        return None
    if argv[1] in ("-h", "--help"):
        print("Usage: python mirror_terms.py [max_downloads]")
        raise SystemExit(0)
    try:
        return int(argv[1])
    except ValueError:
        print("Invalid max_downloads value.")
        raise SystemExit(1)


def main():
    if not os.path.isdir(BASE_DIR):
        print("mirror_raw directory not found", file=sys.stderr)
        return 1
    max_downloads = parse_limit(sys.argv)
    urls = collect_links()
    if not urls:
        print("No URLs found to download.")
        return 0

    downloaded = 0
    skipped = 0
    failed = 0

    for url in sorted(urls):
        dest_path = url_to_path(url)
        if not dest_path:
            continue
        if os.path.exists(dest_path):
            skipped += 1
            continue
        try:
            download(url, dest_path)
            downloaded += 1
            if downloaded % 50 == 0:
                print(f"Downloaded so far: {downloaded}")
            if max_downloads and downloaded >= max_downloads:
                print("Reached download limit.")
                break
        except Exception as exc:
            failed += 1
            print(f"Failed: {url} ({exc})")

    print(f"Downloaded: {downloaded}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
