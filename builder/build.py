#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import html
import json
import math
import re
import shutil
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONTENT_DIR = ROOT / "content" / "truyen"
PAGES_DIR = ROOT / "pages"
TEMPLATES_DIR = ROOT / "templates"
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "_site"

ERRORS = []
WARNINGS = []


def report_ok(message):
    print(f"  ✓ {message}")


def report_warning(message):
    WARNINGS.append(message)
    print(f"  ⚠ {message}")


def report_error(message):
    ERRORS.append(message)
    print(f"  ✗ {message}")


def load_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"Không thể đọc {path}: {error}") from error


def load_json(path):
    try:
        return json.loads(load_text(path))
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"JSON không hợp lệ tại {path}, dòng {error.lineno}, "
            f"cột {error.colno}: {error.msg}"
        ) from error


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_directory(source, destination):
    if not source.exists():
        report_warning(f"Không tìm thấy thư mục {source.relative_to(ROOT)}")
        return

    shutil.copytree(source, destination, dirs_exist_ok=True)


def clean_output():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def is_missing(value):
    return value is None or value == ""


def parse_scalar(value):
    value = value.strip()

    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'"}
    ):
        value = value[1:-1]

    lowered = value.lower()

    if lowered == "true":
        return True

    if lowered == "false":
        return False

    if lowered in {"null", "none"}:
        return None

    if re.fullmatch(r"-?\d+", value):
        return int(value)

    return value


def parse_front_matter(text, source_name):
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")

    if not normalised.startswith("---\n"):
        return {}, normalised

    end_position = normalised.find("\n---\n", 4)

    if end_position == -1:
        raise RuntimeError(
            f"{source_name}: phần thông tin đầu file chưa được đóng bằng ---"
        )

    metadata_text = normalised[4:end_position]
    content = normalised[end_position + 5 :]
    metadata = {}

    for line_number, line in enumerate(metadata_text.splitlines(), start=2):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if ":" not in line:
            raise RuntimeError(
                f"{source_name}, dòng {line_number}: "
                "thông tin phải có dạng tên: giá trị"
            )

        key, value = line.split(":", 1)
        key = key.strip()

        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key):
            raise RuntimeError(
                f"{source_name}, dòng {line_number}: "
                f"tên trường không hợp lệ: {key}"
            )

        metadata[key] = parse_scalar(value)

    return metadata, content.strip()


def slugify(value):
    value = str(value or "").strip().lower()
    value = value.replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def safe_url(value):
    value = str(value or "").strip()

    if not value:
        return ""

    if value.startswith(("/", "#")):
        return value

    parsed = urlparse(value)

    if parsed.scheme in {"http", "https", "mailto"}:
        return value

    return ""


def render_inline(text):
    raw_text = str(text or "")
    tokens = {}

    def replace_link(match):
        label = match.group(1)
        destination = safe_url(match.group(2))

        if not destination:
            return label

        token = f"\x00HVLINK{len(tokens)}\x00"
        external = destination.startswith(("http://", "https://"))
        attributes = ""

        if external:
            attributes = ' target="_blank" rel="noopener noreferrer"'

        tokens[token] = (
            f'<a href="{html.escape(destination, quote=True)}"'
            f"{attributes}>"
            f"{html.escape(label)}</a>"
        )
        return token

    raw_text = re.sub(
        r"\[([^\]\n]+)\]\(([^)\s]+)\)",
        replace_link,
        raw_text,
    )

    rendered = html.escape(raw_text)
    rendered = re.sub(
        r"`([^`\n]+)`",
        r"<code>\1</code>",
        rendered,
    )
    rendered = re.sub(
        r"\*\*([^*\n]+)\*\*",
        r"<strong>\1</strong>",
        rendered,
    )
    rendered = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        r"<em>\1</em>",
        rendered,
    )
    rendered = re.sub(
        r"(?<!_)_([^_\n]+)_(?!_)",
        r"<em>\1</em>",
        rendered,
    )

    for token, link_html in tokens.items():
        rendered = rendered.replace(html.escape(token), link_html)

    return rendered


def markdown_to_html(markdown_text):
    lines = (
        str(markdown_text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    )

    output = []
    paragraph = []
    list_type = None
    list_items = []
    quote_lines = []

    def flush_paragraph():
        nonlocal paragraph

        if paragraph:
            text = " ".join(line.strip() for line in paragraph)
            output.append(f"<p>{render_inline(text)}</p>")
            paragraph = []

    def flush_list():
        nonlocal list_type, list_items

        if list_type and list_items:
            items = "".join(
                f"<li>{render_inline(item)}</li>"
                for item in list_items
            )
            output.append(f"<{list_type}>{items}</{list_type}>")

        list_type = None
        list_items = []

    def flush_quote():
        nonlocal quote_lines

        if quote_lines:
            quote_text = " ".join(quote_lines)
            output.append(
                f"<blockquote><p>{render_inline(quote_text)}</p></blockquote>"
            )
            quote_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        heading_match = re.match(r"^(#{2,4})\s+(.+)$", stripped)
        unordered_match = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered_match = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        quote_match = re.match(r"^>\s?(.*)$", stripped)

        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            flush_paragraph()
            flush_list()
            flush_quote()
            output.append("<hr>")
            continue

        if heading_match:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(heading_match.group(1))
            output.append(
                f"<h{level}>"
                f"{render_inline(heading_match.group(2))}"
                f"</h{level}>"
            )
            continue

        if unordered_match:
            flush_paragraph()
            flush_quote()

            if list_type not in {None, "ul"}:
                flush_list()

            list_type = "ul"
            list_items.append(unordered_match.group(1))
            continue

        if ordered_match:
            flush_paragraph()
            flush_quote()

            if list_type not in {None, "ol"}:
                flush_list()

            list_type = "ol"
            list_items.append(ordered_match.group(1))
            continue

        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines.append(quote_match.group(1))
            continue

        flush_list()
        flush_quote()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    flush_quote()

    return "\n".join(output)


def fill_template(template_text, values):
    result = template_text

    for key, value in values.items():
        result = result.replace(
            "{{" + key + "}}",
            str(value if value is not None else ""),
        )

    unresolved = sorted(
        set(re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", result))
    )

    if unresolved:
        raise RuntimeError(
            "Template còn thiếu dữ liệu: " + ", ".join(unresolved)
        )

    return result


def create_structured_data(data):
    json_text = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    return (
        '<script type="application/ld+json">'
        + json_text
        + "</script>"
    )


def absolute_url(site, path):
    return site["url"].rstrip("/") + "/" + str(path).lstrip("/")


def display_date(value):
    value = str(value or "").strip()

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return value


def short_description(value, maximum=160):
    clean = re.sub(r"\s+", " ", str(value or "")).strip()

    if len(clean) <= maximum:
        return clean

    shortened = clean[: maximum - 1].rsplit(" ", 1)[0]
    return shortened.rstrip(" ,.;:") + "…"


def count_words(value):
    return len(
        re.findall(r"\b[\wÀ-ỹ]+\b", str(value or ""), re.UNICODE)
    )


def reading_minutes(word_count):
    return max(1, math.ceil(word_count / 250))


def is_valid_slug(value):
    return bool(
        re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(value or ""))
    )


def render_base(base_template, site, values):
    defaults = {
        "language": site["language"],
        "locale": site["locale"],
        "site_name": html.escape(site["name"]),
        "tagline": html.escape(site["tagline"]),
        "author": html.escape(site["author"], quote=True),
        "publisher": html.escape(site["publisher"]),
        "logo_path": html.escape(site["logo"], quote=True),
        "logo_url": html.escape(
            absolute_url(site, site["logo"]),
            quote=True,
        ),
        "theme_color": html.escape(
            site["theme_color"],
            quote=True,
        ),
        "copyright_start_year": site["copyright_start_year"],
        "current_year": date.today().year,
        "robots": "index, follow",
        "og_type": "website",
        "social_image_alt": html.escape(
            f"Ảnh đại diện {site['name']}",
            quote=True,
        ),
        "head_extra": "",
        "structured_data": "",
        "body_class": "",
        "body_attributes": "",
        "after_header": "",
        "main_class": "main-content",
        "page_scripts": "",
    }

    defaults.update(values)
    return fill_template(base_template, defaults)


def load_templates():
    template_names = [
        "base",
        "home",
        "book",
        "chapter",
        "page",
        "404",
        "listing",
    ]
    templates = {}

    for name in template_names:
        path = TEMPLATES_DIR / f"{name}.html"

        if not path.exists():
            raise RuntimeError(
                f"Thiếu template: {path.relative_to(ROOT)}"
            )

        templates[name] = load_text(path)

    return templates


def validate_site_config(site):
    required_fields = [
        "name",
        "short_name",
        "tagline",
        "description",
        "url",
        "language",
        "locale",
        "author",
        "publisher",
        "logo",
        "default_cover",
        "social_image",
        "copyright_start_year",
        "theme_color",
        "background_color",
    ]

    for field in required_fields:
        if field not in site or is_missing(site[field]):
            raise RuntimeError(
                f"config/site.json thiếu trường: {field}"
            )

    parsed_url = urlparse(site["url"])

    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise RuntimeError(
            "config/site.json: url phải là địa chỉ HTTPS đầy đủ"
        )


def load_chapters(book_directory):
    chapter_directory = book_directory / "chuong"

    if not chapter_directory.exists():
        return []

    chapters = []
    used_numbers = set()
    used_slugs = set()

    for chapter_path in sorted(chapter_directory.glob("*.md")):
        match = re.fullmatch(
            r"chuong-(\d+)",
            chapter_path.stem,
            re.IGNORECASE,
        )

        if not match:
            report_warning(
                f"Bỏ qua {chapter_path.relative_to(ROOT)}: "
                "tên file phải có dạng chuong-0001.md"
            )
            continue

        metadata, content = parse_front_matter(
            load_text(chapter_path),
            str(chapter_path.relative_to(ROOT)),
        )

        if metadata.get("published", True) is not True:
            continue

        number = int(match.group(1))
        slug = chapter_path.stem.lower()
        title = str(metadata.get("title", "")).strip()
        published_date = str(metadata.get("date", "")).strip()

        if not title:
            report_error(
                f"{chapter_path.relative_to(ROOT)} thiếu title"
            )
            continue

        if not published_date:
            report_error(
                f"{chapter_path.relative_to(ROOT)} thiếu date"
            )
            continue

        try:
            datetime.strptime(published_date, "%Y-%m-%d")
        except ValueError:
            report_error(
                f"{chapter_path.relative_to(ROOT)}: "
                "date phải có dạng YYYY-MM-DD"
            )
            continue

        if not content:
            report_error(
                f"{chapter_path.relative_to(ROOT)} chưa có nội dung"
            )
            continue

        if number in used_numbers:
            report_error(
                f"Trùng số chương {number} trong {book_directory.name}"
            )
            continue

        if slug in used_slugs:
            report_error(
                f"Trùng slug chương {slug} trong {book_directory.name}"
            )
            continue

        used_numbers.add(number)
        used_slugs.add(slug)

        chapters.append(
            {
                "number": number,
                "slug": slug,
                "title": title,
                "date": published_date,
                "content": content,
                "source": chapter_path,
            }
        )

    chapters.sort(key=lambda chapter: chapter["number"])

    for index in range(1, len(chapters)):
        previous_number = chapters[index - 1]["number"]
        current_number = chapters[index]["number"]

        if current_number != previous_number + 1:
            report_warning(
                f"{book_directory.name}: thiếu chương giữa "
                f"{previous_number} và {current_number}"
            )

    return chapters


def clean_string_list(values):
    if not isinstance(values, list):
        return []

    cleaned = []

    for value in values:
        text = str(value or "").strip()

        if text and text not in cleaned:
            cleaned.append(text)

    return cleaned


def load_books():
    if not CONTENT_DIR.exists():
        raise RuntimeError("Chưa có thư mục content/truyen")

    books = []
    used_slugs = set()

    for book_directory in sorted(CONTENT_DIR.iterdir()):
        if not book_directory.is_dir():
            continue

        info_path = book_directory / "info.json"

        if not info_path.exists():
            report_warning(
                f"Bỏ qua {book_directory.name}: thiếu info.json"
            )
            continue

        try:
            info = load_json(info_path)
        except RuntimeError as error:
            report_error(str(error))
            continue

        if info.get("published", True) is not True:
            continue

        required_fields = [
            "slug",
            "title",
            "authors",
            "description",
            "genres",
            "status",
            "language",
            "cover",
            "published_date",
            "updated_date",
            "order",
        ]

        missing_fields = [
            field
            for field in required_fields
            if field not in info or is_missing(info[field])
        ]

        if missing_fields:
            report_error(
                f"{info_path.relative_to(ROOT)} thiếu: "
                + ", ".join(missing_fields)
            )
            continue

        slug = str(info["slug"]).strip().lower()

        if not is_valid_slug(slug):
            report_error(
                f"{info_path.relative_to(ROOT)}: slug không hợp lệ"
            )
            continue

        if slug != book_directory.name:
            report_error(
                f"{info_path.relative_to(ROOT)}: "
                "slug phải giống tên thư mục"
            )
            continue

        if slug in used_slugs:
            report_error(f"Trùng slug truyện: {slug}")
            continue

        authors = clean_string_list(info["authors"])
        genres = clean_string_list(info["genres"])

        if not authors:
            report_error(
                f"{info_path.relative_to(ROOT)}: "
                "authors phải có ít nhất một tác giả"
            )
            continue

        if not genres:
            report_error(
                f"{info_path.relative_to(ROOT)}: "
                "genres phải có ít nhất một thể loại"
            )
            continue

        cover_source = book_directory / str(info["cover"])

        if not cover_source.exists():
            report_warning(
                f"{book_directory.name}: chưa có ảnh {info['cover']}; "
                "sẽ dùng ảnh bìa mặc định"
            )

        chapters = load_chapters(book_directory)

        info["slug"] = slug
        info["authors"] = authors
        info["genres"] = genres
        info["aliases"] = clean_string_list(
            info.get("aliases", [])
        )
        info["featured"] = bool(info.get("featured", False))
        info["chapters"] = chapters
        info["directory"] = book_directory
        info["cover_exists"] = cover_source.exists()

        used_slugs.add(slug)
        books.append(info)

        report_ok(
            f"{info['title']}: {len(chapters)} chương được xuất bản"
        )

    books.sort(
        key=lambda book: (
            int(book.get("order", 999999)),
            book["title"].lower(),
        )
    )

    return books


def public_cover_url(site, book):
    if book["cover_exists"]:
        cover_path = str(book["cover"]).replace("\\", "/")
        return f"/truyen/{book['slug']}/{cover_path}"

    return site["default_cover"]


def copy_book_images(book):
    source_images = book["directory"] / "images"

    if source_images.exists():
        copy_directory(
            source_images,
            OUTPUT_DIR / "truyen" / book["slug"] / "images",
        )


def render_affiliate(affiliate, placement):
    if not affiliate.get("enabled", False):
        return ""

    items = affiliate.get("items", [])

    if not isinstance(items, list) or not items:
        return ""

    rendered_items = []

    for item in items:
        if not isinstance(item, dict):
            continue

        placements = item.get("placements", ["all"])

        if "all" not in placements and placement not in placements:
            continue

        title = str(item.get("title", "")).strip()
        url = safe_url(item.get("url", ""))
        button_text = str(
            item.get("button_text", "Xem thêm")
        ).strip()

        if not title or not url:
            continue

        rendered_items.append(
            '<p><strong>'
            + html.escape(title)
            + '</strong> — <a href="'
            + html.escape(url, quote=True)
            + '" target="_blank" '
            + 'rel="sponsored nofollow noopener noreferrer">'
            + html.escape(button_text)
            + "</a></p>"
        )

    if not rendered_items:
        return ""

    disclosure = html.escape(
        affiliate.get("disclosure", "")
    )

    return (
        '<aside class="affiliate-box" aria-label="Liên kết affiliate">'
        '<p class="affiliate-label">Liên kết affiliate</p>'
        + "".join(rendered_items)
        + f'<p class="affiliate-disclosure">{disclosure}</p>'
        + "</aside>"
    )


def create_book_card(site, book):
    book_url = f"/truyen/{book['slug']}/"
    cover_url = public_cover_url(site, book)
    genres = ", ".join(book["genres"])
    authors = ", ".join(book["authors"])
    aliases = " ".join(book.get("aliases", []))
    search_text = " ".join(
        [
            book["title"],
            authors,
            genres,
            aliases,
            book["description"],
        ]
    )

    return f"""
<article
  class="book-card"
  data-book-card
  data-search-text="{html.escape(search_text, quote=True)}"
>
  <a class="book-cover-link" href="{html.escape(book_url, quote=True)}">
    <img
      class="book-cover"
      src="{html.escape(cover_url, quote=True)}"
      width="400"
      height="600"
      loading="lazy"
      decoding="async"
      alt="Bìa truyện {html.escape(book['title'], quote=True)}"
    >
  </a>

  <div class="book-card-body">
    <h3 class="book-card-title">
      <a href="{html.escape(book_url, quote=True)}">
        {html.escape(book['title'])}
      </a>
    </h3>

    <p class="book-card-author">
      {html.escape(authors)}
    </p>

    <p class="book-card-meta">
      <span>{len(book['chapters'])} chương</span>
      <span>{html.escape(book['status'])}</span>
    </p>
  </div>
</article>
""".strip()


def create_home(site, templates, books):
    book_cards = "\n".join(
        create_book_card(site, book) for book in books
    )

    if not book_cards:
        book_cards = (
            '<div class="empty-state">'
            "<p>Chưa có truyện được xuất bản.</p>"
            "</div>"
        )

    main_content = fill_template(
        templates["home"],
        {
            "site_name": html.escape(site["name"]),
            "site_description": html.escape(site["description"]),
            "book_count": len(books),
            "book_cards": book_cards,
        },
    )

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site["name"],
        "url": site["url"],
        "description": site["description"],
        "inLanguage": site["language"],
        "publisher": {
            "@type": "Organization",
            "name": site["publisher"],
            "url": site["url"],
        },
    }

    html_output = render_base(
        templates["base"],
        site,
        {
            "page_title": html.escape(site["name"]),
            "meta_description": html.escape(
                short_description(site["description"]),
                quote=True,
            ),
            "canonical_url": html.escape(
                site["url"],
                quote=True,
            ),
            "social_image_url": html.escape(
                absolute_url(site, site["social_image"]),
                quote=True,
            ),
            "structured_data": create_structured_data(
                website_schema
            ),
            "main_content": main_content,
            "page_scripts": (
                '<script src="/assets/js/search.js" defer></script>'
            ),
        },
    )

    write_text(OUTPUT_DIR / "index.html", html_output)


def create_author_links(book):
    links = []

    for author in book["authors"]:
        author_slug = slugify(author)
        links.append(
            f'<a href="/tac-gia/{html.escape(author_slug, quote=True)}/">'
            f"<strong>{html.escape(author)}</strong></a>"
        )

    return ", ".join(links)


def create_genre_badges(book):
    badges = []

    for genre in book["genres"]:
        genre_slug = slugify(genre)
        badges.append(
            f'<a class="badge" '
            f'href="/the-loai/{html.escape(genre_slug, quote=True)}/">'
            f"{html.escape(genre)}</a>"
        )

    return "\n".join(badges)


def create_aliases(book):
    aliases = book.get("aliases", [])

    if not aliases:
        return ""

    return (
        '<p class="book-detail-author">'
        "Tên khác: "
        + html.escape(", ".join(aliases))
        + "</p>"
    )


def create_chapter_items(book):
    if not book["chapters"]:
        return (
            '<li class="empty-state">'
            "<p>Truyện chưa có chương được xuất bản.</p>"
            "</li>"
        )

    items = []

    for chapter in book["chapters"]:
        chapter_url = (
            f"/truyen/{book['slug']}/chuong/"
            f"{chapter['slug']}.html"
        )
        items.append(
            '<li class="chapter-item">'
            f'<a class="chapter-link" '
            f'href="{html.escape(chapter_url, quote=True)}">'
            f'<span class="chapter-title">'
            f'{html.escape(chapter["title"])}</span>'
            f'<time class="chapter-date" '
            f'datetime="{html.escape(chapter["date"], quote=True)}">'
            f'{html.escape(display_date(chapter["date"]))}</time>'
            "</a></li>"
        )

    return "\n".join(items)


def create_reading_buttons(book):
    if not book["chapters"]:
        return (
            '<span class="secondary-button" aria-disabled="true">'
            "Chưa có chương"
            "</span>"
        )

    first_chapter = book["chapters"][0]
    first_url = (
        f"/truyen/{book['slug']}/chuong/"
        f"{first_chapter['slug']}.html"
    )

    return (
        f'<a class="primary-button" '
        f'href="{html.escape(first_url, quote=True)}">'
        "Đọc từ đầu"
        "</a>"
        f'<a class="secondary-button" '
        f'href="{html.escape(first_url, quote=True)}" '
        f'data-resume-link '
        f'data-book-slug="{html.escape(book["slug"], quote=True)}" '
        "hidden>Đọc tiếp</a>"
    )


def create_book_page(site, affiliate, templates, book):
    book_path = f"/truyen/{book['slug']}/"
    canonical = absolute_url(site, book_path)
    cover_url = public_cover_url(site, book)
    absolute_cover = absolute_url(site, cover_url)

    main_content = fill_template(
        templates["book"],
        {
            "book_title": html.escape(book["title"]),
            "book_title_attribute": html.escape(
                book["title"],
                quote=True,
            ),
            "book_authors": create_author_links(book),
            "book_status": html.escape(book["status"]),
            "book_cover_url": html.escape(
                cover_url,
                quote=True,
            ),
            "genre_badges": create_genre_badges(book),
            "book_aliases": create_aliases(book),
            "book_description": markdown_to_html(
                book["description"]
            ),
            "reading_buttons": create_reading_buttons(book),
            "book_share_text_attribute": html.escape(
                short_description(book["description"]),
                quote=True,
            ),
            "canonical_url": html.escape(
                canonical,
                quote=True,
            ),
            "affiliate_content": render_affiliate(
                affiliate,
                "book",
            ),
            "chapter_count": len(book["chapters"]),
            "chapter_items": create_chapter_items(book),
        },
    )

    book_schema = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": book["title"],
        "description": book["description"],
        "url": canonical,
        "image": absolute_cover,
        "inLanguage": book["language"],
        "author": [
            {
                "@type": "Person",
                "name": author,
                "url": absolute_url(
                    site,
                    f"/tac-gia/{slugify(author)}/",
                ),
            }
            for author in book["authors"]
        ],
        "genre": book["genres"],
        "datePublished": book["published_date"],
        "dateModified": book["updated_date"],
    }

    html_output = render_base(
        templates["base"],
        site,
        {
            "page_title": html.escape(
                f"{book['title']} | {site['name']}"
            ),
            "meta_description": html.escape(
                short_description(book["description"]),
                quote=True,
            ),
            "canonical_url": html.escape(
                canonical,
                quote=True,
            ),
            "og_type": "article",
            "social_image_url": html.escape(
                absolute_cover,
                quote=True,
            ),
            "social_image_alt": html.escape(
                f"Bìa truyện {book['title']}",
                quote=True,
            ),
            "structured_data": create_structured_data(
                book_schema
            ),
            "main_content": main_content,
        },
    )

    destination = (
        OUTPUT_DIR / "truyen" / book["slug"] / "index.html"
    )
    write_text(destination, html_output)


def navigation_link(book, chapter, direction):
    if chapter is None:
        return (
            '<span class="chapter-navigation-link disabled" '
            'aria-hidden="true"></span>'
        )

    url = (
        f"/truyen/{book['slug']}/chuong/"
        f"{chapter['slug']}.html"
    )
    is_previous = direction == "previous"
    css_class = "" if is_previous else " next"
    data_attribute = (
        "data-previous-chapter"
        if is_previous
        else "data-next-chapter"
    )
    direction_text = (
        "Chương trước" if is_previous else "Chương sau"
    )

    return (
        f'<a class="chapter-navigation-link{css_class}" '
        f'href="{html.escape(url, quote=True)}" {data_attribute}>'
        f'<span class="chapter-navigation-direction">'
        f"{direction_text}</span>"
        f'<span class="chapter-navigation-title">'
        f'{html.escape(chapter["title"])}</span>'
        "</a>"
    )


def create_chapter_page(
    site,
    affiliate,
    templates,
    book,
    chapter,
    previous_chapter,
    next_chapter,
):
    book_url = f"/truyen/{book['slug']}/"
    chapter_path = (
        f"/truyen/{book['slug']}/chuong/"
        f"{chapter['slug']}.html"
    )
    canonical = absolute_url(site, chapter_path)
    cover_url = public_cover_url(site, book)
    absolute_cover = absolute_url(site, cover_url)
    word_total = count_words(chapter["content"])
    authors_text = ", ".join(book["authors"])

    main_content = fill_template(
        templates["chapter"],
        {
            "book_url": html.escape(book_url, quote=True),
            "book_title": html.escape(book["title"]),
            "book_title_attribute": html.escape(
                book["title"],
                quote=True,
            ),
            "chapter_title": html.escape(chapter["title"]),
            "chapter_share_title_attribute": html.escape(
                f"{chapter['title']} – {book['title']}",
                quote=True,
            ),
            "chapter_share_text_attribute": html.escape(
                f"Đọc {chapter['title']} của {book['title']} "
                f"trên {site['name']}.",
                quote=True,
            ),
            "canonical_url": html.escape(
                canonical,
                quote=True,
            ),
            "chapter_date_display": html.escape(
                display_date(chapter["date"])
            ),
            "word_count": word_total,
            "reading_time": reading_minutes(word_total),
            "chapter_content": markdown_to_html(
                chapter["content"]
            ),
            "affiliate_content": render_affiliate(
                affiliate,
                "chapter",
            ),
            "previous_chapter_link": navigation_link(
                book,
                previous_chapter,
                "previous",
            ),
            "next_chapter_link": navigation_link(
                book,
                next_chapter,
                "next",
            ),
        },
    )

    chapter_schema = {
        "@context": "https://schema.org",
        "@type": "Chapter",
        "name": chapter["title"],
        "url": canonical,
        "datePublished": chapter["date"],
        "inLanguage": book["language"],
        "isPartOf": {
            "@type": "Book",
            "name": book["title"],
            "url": absolute_url(site, book_url),
        },
        "author": [
            {
                "@type": "Person",
                "name": author,
            }
            for author in book["authors"]
        ],
    }

    body_attributes = (
        f'data-book-slug="{html.escape(book["slug"], quote=True)}" '
        f'data-book-title="{html.escape(book["title"], quote=True)}" '
        f'data-chapter-slug="{html.escape(chapter["slug"], quote=True)}" '
        f'data-chapter-title="{html.escape(chapter["title"], quote=True)}" '
        f'data-chapter-number="{chapter["number"]}"'
    )

    meta_description = short_description(
        f"{chapter['title']} thuộc truyện {book['title']} "
        f"của {authors_text}. Đọc truyện tại {site['name']}."
    )

    html_output = render_base(
        templates["base"],
        site,
        {
            "page_title": html.escape(
                f"{chapter['title']} – "
                f"{book['title']} | {site['name']}"
            ),
            "meta_description": html.escape(
                meta_description,
                quote=True,
            ),
            "canonical_url": html.escape(
                canonical,
                quote=True,
            ),
            "og_type": "article",
            "social_image_url": html.escape(
                absolute_cover,
                quote=True,
            ),
            "social_image_alt": html.escape(
                f"Bìa truyện {book['title']}",
                quote=True,
            ),
            "head_extra": (
                '<link rel="stylesheet" '
                'href="/assets/css/reader.css">'
            ),
            "structured_data": create_structured_data(
                chapter_schema
            ),
            "body_class": "reader-page",
            "body_attributes": body_attributes,
            "main_class": "",
            "main_content": main_content,
            "page_scripts": (
                '<script src="/assets/js/reader.js" defer></script>'
            ),
        },
    )

    destination = (
        OUTPUT_DIR
        / "truyen"
        / book["slug"]
        / "chuong"
        / f"{chapter['slug']}.html"
    )
    write_text(destination, html_output)


def create_all_book_pages(site, affiliate, templates, books):
    for book in books:
        copy_book_images(book)
        create_book_page(site, affiliate, templates, book)

        for index, chapter in enumerate(book["chapters"]):
            previous_chapter = (
                book["chapters"][index - 1]
                if index > 0
                else None
            )
            next_chapter = (
                book["chapters"][index + 1]
                if index + 1 < len(book["chapters"])
                else None
            )

            create_chapter_page(
                site,
                affiliate,
                templates,
                book,
                chapter,
                previous_chapter,
                next_chapter,
            )


def build_taxonomy_groups(books, field):
    groups = {}
    names_by_slug = {}

    for book in books:
        for name in book[field]:
            item_slug = slugify(name)

            if not item_slug:
                report_error(
                    f"Không thể tạo đường dẫn cho: {name}"
                )
                continue

            existing_name = names_by_slug.get(item_slug)

            if existing_name and existing_name != name:
                report_error(
                    f"Hai tên tạo cùng đường dẫn '{item_slug}': "
                    f"'{existing_name}' và '{name}'"
                )
                continue

            names_by_slug[item_slug] = name

            if item_slug not in groups:
                groups[item_slug] = {
                    "slug": item_slug,
                    "name": name,
                    "books": [],
                }

            groups[item_slug]["books"].append(book)

    return dict(
        sorted(
            groups.items(),
            key=lambda item: item[1]["name"].lower(),
        )
    )


def create_taxonomy_index_content(groups, root_path):
    if not groups:
        return (
            '<div class="empty-state">'
            "<p>Chưa có dữ liệu để hiển thị.</p>"
            "</div>"
        )

    items = []

    for group in groups.values():
        group_url = f"/{root_path}/{group['slug']}/"
        items.append(
            '<li class="chapter-item">'
            f'<a class="chapter-link" '
            f'href="{html.escape(group_url, quote=True)}">'
            f'<span class="chapter-title">'
            f'{html.escape(group["name"])}</span>'
            f'<span class="chapter-date">'
            f'{len(group["books"])} truyện</span>'
            "</a></li>"
        )

    return (
        '<div class="chapter-panel">'
        '<ul class="chapter-list">'
        + "\n".join(items)
        + "</ul></div>"
    )


def render_listing_page(
    site,
    templates,
    title,
    description,
    canonical_path,
    breadcrumb_items,
    listing_content,
):
    canonical = absolute_url(site, canonical_path)

    main_content = fill_template(
        templates["listing"],
        {
            "breadcrumb_items": breadcrumb_items,
            "listing_title": html.escape(title),
            "listing_description": html.escape(description),
            "listing_content": listing_content,
        },
    )

    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical,
        "inLanguage": site["language"],
        "isPartOf": {
            "@type": "WebSite",
            "name": site["name"],
            "url": site["url"],
        },
    }

    return render_base(
        templates["base"],
        site,
        {
            "page_title": html.escape(
                f"{title} | {site['name']}"
            ),
            "meta_description": html.escape(
                short_description(description),
                quote=True,
            ),
            "canonical_url": html.escape(
                canonical,
                quote=True,
            ),
            "social_image_url": html.escape(
                absolute_url(site, site["social_image"]),
                quote=True,
            ),
            "structured_data": create_structured_data(schema),
            "main_content": main_content,
        },
    )


def create_taxonomy_pages(site, templates, books, taxonomy):
    if taxonomy == "genres":
        root_path = "the-loai"
        index_title = "Thể loại truyện"
        index_description = (
            "Khám phá các tác phẩm trên Huyền Võng "
            "được sắp xếp theo thể loại."
        )
        item_label = "Thể loại"
    else:
        root_path = "tac-gia"
        index_title = "Tác giả"
        index_description = (
            "Khám phá các tác phẩm trên Huyền Võng "
            "được sắp xếp theo tác giả."
        )
        item_label = "Tác giả"

    groups = build_taxonomy_groups(books, taxonomy)
    sitemap_items = []

    index_content = create_taxonomy_index_content(
        groups,
        root_path,
    )
    index_html = render_listing_page(
        site=site,
        templates=templates,
        title=index_title,
        description=index_description,
        canonical_path=f"/{root_path}/",
        breadcrumb_items=(
            f'<li aria-current="page">{html.escape(index_title)}</li>'
        ),
        listing_content=index_content,
    )

    write_text(
        OUTPUT_DIR / root_path / "index.html",
        index_html,
    )
    sitemap_items.append(
        {
            "url": f"/{root_path}/",
            "updated_date": date.today().isoformat(),
        }
    )

    for group in groups.values():
        group_title = f"{item_label}: {group['name']}"
        group_description = (
            f"Danh sách {len(group['books'])} truyện thuộc "
            f"{item_label.lower()} {group['name']} trên {site['name']}."
        )
        book_cards = "\n".join(
            create_book_card(site, book)
            for book in group["books"]
        )
        listing_content = (
            '<section class="section" aria-label="Danh sách truyện">'
            '<div class="book-grid">'
            + book_cards
            + "</div></section>"
        )
        group_path = f"/{root_path}/{group['slug']}/"
        breadcrumb_items = (
            f'<li><a href="/{root_path}/">'
            f"{html.escape(index_title)}</a></li>"
            f'<li aria-current="page">'
            f'{html.escape(group["name"])}</li>'
        )

        group_html = render_listing_page(
            site=site,
            templates=templates,
            title=group_title,
            description=group_description,
            canonical_path=group_path,
            breadcrumb_items=breadcrumb_items,
            listing_content=listing_content,
        )

        write_text(
            OUTPUT_DIR
            / root_path
            / group["slug"]
            / "index.html",
            group_html,
        )
        sitemap_items.append(
            {
                "url": group_path,
                "updated_date": max(
                    (
                        str(book["updated_date"])
                        for book in group["books"]
                    ),
                    default=date.today().isoformat(),
                ),
            }
        )

    return sitemap_items


def create_content_pages(site, templates):
    pages = []

    if not PAGES_DIR.exists():
        report_warning("Chưa có thư mục pages")
        return pages

    for page_path in sorted(PAGES_DIR.glob("*.md")):
        metadata, markdown_content = parse_front_matter(
            load_text(page_path),
            str(page_path.relative_to(ROOT)),
        )

        title = str(metadata.get("title", "")).strip()
        description = str(
            metadata.get("description", "")
        ).strip()
        slug = page_path.stem.lower()

        if not title or not description:
            report_error(
                f"{page_path.relative_to(ROOT)} "
                "thiếu title hoặc description"
            )
            continue

        if not is_valid_slug(slug):
            report_error(
                f"Tên trang không hợp lệ: {page_path.name}"
            )
            continue

        page_url = f"/{slug}/"
        canonical = absolute_url(site, page_url)

        main_content = fill_template(
            templates["page"],
            {
                "page_heading": html.escape(title),
                "page_summary": html.escape(description),
                "page_content": markdown_to_html(
                    markdown_content
                ),
            },
        )

        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": canonical,
            "inLanguage": site["language"],
            "isPartOf": {
                "@type": "WebSite",
                "name": site["name"],
                "url": site["url"],
            },
        }

        html_output = render_base(
            templates["base"],
            site,
            {
                "page_title": html.escape(
                    f"{title} | {site['name']}"
                ),
                "meta_description": html.escape(
                    short_description(description),
                    quote=True,
                ),
                "canonical_url": html.escape(
                    canonical,
                    quote=True,
                ),
                "social_image_url": html.escape(
                    absolute_url(site, site["social_image"]),
                    quote=True,
                ),
                "structured_data": create_structured_data(
                    schema
                ),
                "main_content": main_content,
            },
        )

        write_text(
            OUTPUT_DIR / slug / "index.html",
            html_output,
        )

        pages.append(
            {
                "url": page_url,
                "updated_date": date.today().isoformat(),
            }
        )

    return pages


def create_404(site, templates):
    canonical = absolute_url(site, "/404.html")
    main_content = fill_template(templates["404"], {})

    html_output = render_base(
        templates["base"],
        site,
        {
            "page_title": html.escape(
                f"Không tìm thấy trang | {site['name']}"
            ),
            "meta_description": html.escape(
                "Trang bạn đang tìm không tồn tại.",
                quote=True,
            ),
            "canonical_url": html.escape(
                canonical,
                quote=True,
            ),
            "robots": "noindex, follow",
            "social_image_url": html.escape(
                absolute_url(site, site["social_image"]),
                quote=True,
            ),
            "main_content": main_content,
        },
    )

    write_text(OUTPUT_DIR / "404.html", html_output)


def create_robots(site):
    content = (
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {absolute_url(site, '/sitemap.xml')}\n"
    )
    write_text(OUTPUT_DIR / "robots.txt", content)


def create_sitemap(site, books, pages, taxonomy_pages):
    urls = [
        {
            "url": "/",
            "updated_date": date.today().isoformat(),
        }
    ]

    urls.extend(pages)
    urls.extend(taxonomy_pages)

    for book in books:
        urls.append(
            {
                "url": f"/truyen/{book['slug']}/",
                "updated_date": book["updated_date"],
            }
        )

        for chapter in book["chapters"]:
            urls.append(
                {
                    "url": (
                        f"/truyen/{book['slug']}/chuong/"
                        f"{chapter['slug']}.html"
                    ),
                    "updated_date": chapter["date"],
                }
            )

    entries = []

    for item in urls:
        entries.append(
            "  <url>\n"
            f"    <loc>"
            f"{xml_escape(absolute_url(site, item['url']))}"
            f"</loc>\n"
            f"    <lastmod>"
            f"{xml_escape(str(item['updated_date']))}"
            f"</lastmod>\n"
            "  </url>"
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset '
        'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )

    write_text(OUTPUT_DIR / "sitemap.xml", sitemap)


def create_nojekyll():
    write_text(OUTPUT_DIR / ".nojekyll", "")


def main():
    print("\nHV Static Builder")
    print("=================\n")

    try:
        site = load_json(CONFIG_DIR / "site.json")
        affiliate = load_json(CONFIG_DIR / "affiliate.json")
        validate_site_config(site)
        templates = load_templates()

        clean_output()
        copy_directory(ASSETS_DIR, OUTPUT_DIR / "assets")

        print("Kiểm tra nội dung truyện:")
        books = load_books()

        create_home(site, templates, books)
        create_all_book_pages(
            site,
            affiliate,
            templates,
            books,
        )

        taxonomy_pages = []
        taxonomy_pages.extend(
            create_taxonomy_pages(
                site,
                templates,
                books,
                "genres",
            )
        )
        taxonomy_pages.extend(
            create_taxonomy_pages(
                site,
                templates,
                books,
                "authors",
            )
        )

        pages = create_content_pages(site, templates)
        create_404(site, templates)
        create_robots(site)
        create_sitemap(
            site,
            books,
            pages,
            taxonomy_pages,
        )
        create_nojekyll()

    except RuntimeError as error:
        report_error(str(error))
    except OSError as error:
        report_error(f"Lỗi hệ thống tệp: {error}")
    except Exception as error:
        report_error(f"Lỗi không xác định: {error}")

    print("\nKết quả")
    print("=======")
    print(f"Lỗi: {len(ERRORS)}")
    print(f"Cảnh báo: {len(WARNINGS)}")

    if ERRORS:
        print("\nWebsite chưa được tạo vì còn lỗi.")
        return 1

    print(
        "\n✓ Website đã được tạo thành công "
        "trong thư mục _site"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
