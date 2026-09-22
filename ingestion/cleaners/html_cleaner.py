from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from .text_cleaner import clean_text

REMOVE_TAGS = {
    "script", "style", "noscript", "svg", "canvas", "iframe",
    "nav", "footer", "form", "button", "aside", "header",
}

# Ordered from specific/high-confidence content containers to broader fallbacks.
ARTICLE_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    "#main-content",
    "#main_content",
    "#mainbody",
    "#main-body",
    "#content",
    "#main",
    ".main-content",
    ".main_content",
    ".content-main",
    ".content",
    ".usa-prose",
    "#fact-sheet-content",
    ".fact-sheet-content",
]

# Common navigation/social/footer furniture not always represented by semantic
# <nav>/<footer> elements. These selectors are intentionally conservative.
REMOVE_SELECTORS = [
    ".breadcrumb", ".breadcrumbs", "[aria-label='breadcrumb']",
    ".site-footer", ".page-footer", ".footer",
    ".site-header", ".page-header .utility", ".utility-nav",
    ".social-media", ".social-links", ".share", ".share-buttons",
    ".addthis_tool", ".addthis_inline_share_toolbox",
    ".print-button", ".print-link",
    ".cookie-banner", ".cookie-notice",
    ".usa-banner", ".usa-header", ".usa-footer",
    ".left-nav", ".side-nav", ".sidenav", ".sidebar",
    ".cdc-page-navigation", ".cdc-page-footer", ".cdc-page-info",
    ".cdc-page-source", ".cdc-dfe-body__right-rail",
    ".cdc-dfe-body__sidebar", ".cdc-dfe-body__utility",
    ".cdc-dfe-body__social", ".cdc-dfe-body__footer",
    ".cdc-dfe-body__related", ".cdc-dfe-body__resources",
]

BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd", "blockquote", "figcaption"}

# Metadata/footer labels that commonly mark the end of the useful article on
# CDC/NIH templates. These are only used late in the page, never globally.
TRAILING_METADATA_MARKERS = {
    "published:",
    "updated:",
    "reviewed:",
    "content source",
    "sources and page info",
    "about this page",
}

# Some CDC templates omit the explicit Published/Updated/Reviewed labels after
# article content and instead emit explanatory maintenance sentences. These
# prefixes are intentionally narrow and are only used when pruning late-page
# metadata, so normal medical prose is not affected.
TRAILING_METADATA_PREFIXES = (
    "this page was last updated on this date",
    "updates may include minor edits, image changes, or other modifications to page content",
    "the information on this page was last reviewed by subject matter experts to ensure accuracy",
    "this page was last reviewed on",
)

# A trailing Resources section on government pages is often a set of related
# cards/links, not the article itself. We remove it only when it occurs in the
# latter half of the page and the following blocks look card-like.
RESOURCE_SECTION_HEADINGS = {
    "resources",
    "related links",
    "additional resources",
    "for health care professionals",
}


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" ", strip=True))
    if soup.title:
        return clean_text(soup.title.get_text(" ", strip=True))
    return ""


def _remove_link_heavy_blocks(soup: BeautifulSoup) -> None:
    """Remove compact containers that are overwhelmingly collections of links.

    This catches related-resource grids/cards while avoiding ordinary article
    paragraphs that merely contain a few inline citations or links.
    """
    candidates = list(soup.find_all(["div", "section", "ul", "ol"]))
    for tag in reversed(candidates):
        if tag.parent is None:
            continue
        links = tag.find_all("a")
        if len(links) < 3:
            continue
        total_text = " ".join(tag.stripped_strings)
        if not total_text:
            continue
        word_count = len(total_text.split())
        if word_count > 180:
            continue
        link_text = " ".join(" ".join(a.stripped_strings) for a in links)
        if not link_text:
            continue
        ratio = len(link_text) / max(len(total_text), 1)
        # Related-card blocks often include one-line descriptions, so v5 uses a
        # slightly lower threshold than v4 while still requiring 3+ links.
        if ratio >= 0.72:
            tag.decompose()


def _remove_page_furniture(soup: BeautifulSoup) -> None:
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for selector in REMOVE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    for tag in soup.select("[hidden], [aria-hidden='true']"):
        tag.decompose()

    _remove_link_heavy_blocks(soup)


def _is_nested_block(tag: Tag) -> bool:
    """Return True when a block's text will be emitted by a child block.

    For example, <li><p>text</p></li> should not emit both the <li> and <p>.
    """
    return any(isinstance(child, Tag) and child.name in BLOCK_TAGS for child in tag.children)


def _extract_blocks(container: Tag | BeautifulSoup) -> list[str]:
    """Extract semantic text blocks while keeping inline links inline.

    v4 used get_text("\\n"), which inserted paragraph breaks around inline
    <a>/<strong>/<em> elements. v5 instead emits one cleaned string per block
    element using get_text(" "), so a linked phrase stays in its sentence.
    """
    blocks: list[str] = []
    for tag in container.find_all(list(BLOCK_TAGS)):
        if _is_nested_block(tag):
            continue
        value = clean_text(tag.get_text(" ", strip=True))
        if value:
            blocks.append(value)

    if blocks:
        return blocks

    fallback = clean_text(container.get_text(" ", strip=True))
    return [fallback] if fallback else []


def _is_trailing_metadata_block(block: str) -> bool:
    normalized = block.strip().lower()
    if normalized in TRAILING_METADATA_MARKERS:
        return True
    return any(normalized.startswith(prefix) for prefix in TRAILING_METADATA_PREFIXES)


def _looks_like_resource_tail(blocks: list[str], start: int) -> bool:
    tail = blocks[start + 1:]
    if not tail:
        return False

    # Stop analysis when page metadata starts; resource-card sections usually
    # appear directly before the metadata/footer. CDC sometimes uses full
    # maintenance sentences instead of explicit Updated:/Reviewed: labels.
    content_tail: list[str] = []
    for block in tail:
        if _is_trailing_metadata_block(block):
            break
        content_tail.append(block)

    if not content_tail:
        return True

    # Examine at most the first 16 blocks after the heading. Related-resource
    # cards tend to be title/description pairs with short blocks.
    sample = content_tail[:16]
    lengths = [len(item.split()) for item in sample]
    short = sum(length <= 18 for length in lengths)
    very_long = sum(length >= 55 for length in lengths)
    return short / len(sample) >= 0.65 and very_long == 0


def _words_before(blocks: list[str], index: int) -> int:
    return sum(len(block.split()) for block in blocks[:index])


def _prune_resource_card_tail(blocks: list[str]) -> list[str]:
    if len(blocks) < 4:
        return blocks
    for index, block in enumerate(blocks):
        label = block.strip().lower()
        # Position is measured by article words rather than block count because
        # one long paragraph may represent most of a page. Require substantial
        # article prose before pruning a Resources-style tail.
        if (
            label in RESOURCE_SECTION_HEADINGS
            and _words_before(blocks, index) >= 60
            and _looks_like_resource_tail(blocks, index)
        ):
            return blocks[:index]
    return blocks


def _prune_trailing_metadata(blocks: list[str]) -> list[str]:
    """Trim late publication/review metadata, not normal article prose.

    If CDC-style maintenance text follows a late Resources heading directly,
    trim from the Resources heading so the vector corpus does not keep a
    meaningless trailing heading by itself.
    """
    if not blocks:
        return blocks
    for index, block in enumerate(blocks):
        if _is_trailing_metadata_block(block) and _words_before(blocks, index) >= 60:
            start = index
            if index > 0 and blocks[index - 1].strip().lower() in RESOURCE_SECTION_HEADINGS:
                start = index - 1
            return blocks[:start]
    return blocks


def _container_text(container: Tag | BeautifulSoup) -> str:
    blocks = _extract_blocks(container)
    blocks = _prune_resource_card_tail(blocks)
    blocks = _prune_trailing_metadata(blocks)
    return "\n\n".join(blocks).strip()


def _word_count(text: str) -> int:
    return len((text or "").split())


def extract_article_text(html: str | bytes, min_preferred_words: int = 80) -> tuple[str, str]:
    """Return ``(title, cleaned_text)`` from an HTML document.

    Raw response bytes are preferred so BeautifulSoup/lxml can honor the
    document charset. The extractor keeps inline hyperlink text within its
    surrounding sentence, removes high-confidence resource-card tails, and
    trims trailing page metadata.
    """
    soup = BeautifulSoup(html, "lxml")
    title = extract_title(soup)
    _remove_page_furniture(soup)

    best_text = ""
    for selector in ARTICLE_SELECTORS:
        container = soup.select_one(selector)
        if container is None:
            continue
        candidate = _container_text(container)
        if _word_count(candidate) > _word_count(best_text):
            best_text = candidate
        if _word_count(candidate) >= min_preferred_words:
            return title, candidate

    body_text = _container_text(soup.body or soup)
    if _word_count(body_text) > _word_count(best_text):
        best_text = body_text

    return title, best_text
