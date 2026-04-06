import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request


BASE_URLS = [
    "https://www.aspaklaria.info/",
    "http://www.aspaklaria.info/",
]

LETTER_INDEXES = [
    ("100_QOF", ["QOF.html", "QOF.htm"]),
    ("200_RESH", ["RESH.html", "RESH.htm"]),
    ("300_SHIN", ["SHIN.html", "SHIN.htm"]),
    ("400_TAV", ["TAV.html", "TAV.htm"]),
]

OUTPUT_ROOT = os.path.join(os.getcwd(), "mirror_httrack_refill", "www.aspaklaria.info")
RAW_OUTPUT = False
OVERWRITE = False

HREF_RE = re.compile(r"href\s*=\s*(\".*?\"|'.*?'|[^\s>]+)", re.IGNORECASE)


def normalize_url(url):
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote_plus(parts.query, safe="=&%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def fetch_url(url):
    safe_url = normalize_url(url)
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), response.geturl()


def try_fetch(paths):
    last_error = None
    for base in BASE_URLS:
        for path in paths:
            url = urllib.parse.urljoin(base, path)
            try:
                data, final_url = fetch_url(url)
                return data, final_url
            except Exception as exc:
                last_error = exc
    raise last_error


def encode_path(path):
    normalized = urllib.parse.unquote(path)
    return urllib.parse.quote(normalized, safe="/%?=&:#.-_")


def write_bytes(rel_path, data):
    if RAW_OUTPUT:
        out_path = os.path.join(OUTPUT_ROOT, rel_path.replace("/", os.sep))
    else:
        encoded = encode_path(rel_path.replace("\\", "/"))
        out_path = os.path.join(OUTPUT_ROOT, encoded.replace("/", os.sep))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(data)
    return out_path


def output_exists(rel_path, min_size=0):
    if RAW_OUTPUT:
        out_path = os.path.join(OUTPUT_ROOT, rel_path.replace("/", os.sep))
    else:
        encoded = encode_path(rel_path.replace("\\", "/"))
        out_path = os.path.join(OUTPUT_ROOT, encoded.replace("/", os.sep))
    if not os.path.exists(out_path):
        return False
    if min_size:
        try:
            return os.path.getsize(out_path) >= min_size
        except OSError:
            return False
    return True


def extract_links(content, base_url):
    text = content.decode("utf-8", errors="ignore")
    links = []
    for match in HREF_RE.finditer(text):
        raw = match.group(1).strip("\"'")
        if not raw:
            continue
        raw = html.unescape(raw)
        lower = raw.lower()
        if lower.startswith(("mailto:", "javascript:", "tel:", "#")):
            continue
        if ".htm" not in lower and ".html" not in lower:
            continue
        full = urllib.parse.urljoin(base_url, raw)
        links.append(full)
    return links


def download_letter(folder, index_names, max_downloads=None, min_size=0):
    index_paths = [f"{folder}/{name}" for name in index_names]
    index_data, final_url = try_fetch(index_paths)
    index_rel = f"{folder}/{index_names[0]}"
    write_bytes(index_rel, index_data)

    links = extract_links(index_data, final_url)
    print(f"{folder}: {len(set(links))} links in index")
    downloaded = 0
    for link in sorted(set(links)):
        parts = urllib.parse.urlsplit(link)
        if parts.netloc not in ("www.aspaklaria.info", "aspaklaria.info"):
            continue
        if not parts.path.startswith(f"/{folder}/"):
            continue
        rel_path = parts.path.lstrip("/")
        if not OVERWRITE and output_exists(rel_path, min_size=min_size):
            continue
        try:
            data, _final = fetch_url(link)
            write_bytes(rel_path, data)
            downloaded += 1
            if downloaded % 50 == 0:
                print(f"{folder}: downloaded {downloaded}")
            if max_downloads and downloaded >= max_downloads:
                break
            time.sleep(0.05)
        except Exception as exc:
            safe_link = link.encode("utf-8", errors="backslashreplace").decode("ascii", errors="ignore")
            safe_exc = str(exc).encode("utf-8", errors="backslashreplace").decode("ascii", errors="ignore")
            print(f"Failed: {safe_link} ({safe_exc})")
    return downloaded


def parse_args(argv):
    folders = None
    max_downloads = None
    output_root = None
    raw_output = False
    overwrite = False
    min_size = 0
    for arg in argv[1:]:
        if arg.startswith("--max="):
            try:
                max_downloads = int(arg.split("=", 1)[1])
            except ValueError:
                raise SystemExit("Invalid --max value")
        elif arg.startswith("--output="):
            output_root = arg.split("=", 1)[1].strip()
        elif arg == "--raw-names":
            raw_output = True
        elif arg == "--overwrite":
            overwrite = True
        elif arg.startswith("--min-size="):
            try:
                min_size = int(arg.split("=", 1)[1])
            except ValueError:
                raise SystemExit("Invalid --min-size value")
        else:
            folders = folders or []
            folders.append(arg)
    return folders, max_downloads, output_root, raw_output, overwrite, min_size


def main():
    global OUTPUT_ROOT, RAW_OUTPUT, OVERWRITE
    folders, max_downloads, output_root, raw_output, overwrite, min_size = parse_args(sys.argv)
    if output_root:
        OUTPUT_ROOT = output_root
    RAW_OUTPUT = raw_output
    OVERWRITE = overwrite
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    total = 0
    targets = LETTER_INDEXES
    if folders:
        wanted = set(folders)
        targets = [item for item in LETTER_INDEXES if item[0] in wanted]
    for folder, index_names in targets:
        print(f"Fetching {folder}...")
        count = download_letter(folder, index_names, max_downloads, min_size)
        total += count
        print(f"{folder}: {count} pages downloaded")
    print(f"Total downloaded: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
