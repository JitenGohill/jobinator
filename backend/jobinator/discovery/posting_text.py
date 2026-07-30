from html.parser import HTMLParser


class _PostingTextParser(HTMLParser):
    _REQUIREMENT_HEADINGS = ("requirement", "qualification", "what we're looking for")
    _BLOCK_TAGS = {"div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p"}

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.requirements: list[str] = []
        self._line_parts: list[str] = []
        self._heading_parts: list[str] | None = None
        self._strong_parts: list[str] | None = None
        self._list_item_parts: list[str] | None = None
        self._current_heading = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._BLOCK_TAGS:
            self._flush_line()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_parts = []
        elif tag == "li":
            self._list_item_parts = []
        elif tag == "strong":
            self._strong_parts = []
        elif tag == "br":
            self._flush_line()

    def handle_data(self, data: str) -> None:
        self._line_parts.append(data)
        if self._heading_parts is not None:
            self._heading_parts.append(data)
        if self._strong_parts is not None:
            self._strong_parts.append(data)
        if self._list_item_parts is not None:
            self._list_item_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading_parts is not None:
            heading = self._clean(self._heading_parts)
            self._current_heading = heading.lower()
            self._heading_parts = None
        elif tag == "li" and self._list_item_parts is not None:
            item = self._clean(self._list_item_parts)
            if item and any(
                marker in self._current_heading for marker in self._REQUIREMENT_HEADINGS
            ):
                self.requirements.append(item)
            self._list_item_parts = None
        elif tag == "strong" and self._strong_parts is not None:
            emphasized_text = self._clean(self._strong_parts)
            if self._list_item_parts is None:
                self._current_heading = emphasized_text.lower()
            self._strong_parts = None

        if tag in self._BLOCK_TAGS:
            self._flush_line()

    @staticmethod
    def _clean(parts: list[str]) -> str:
        return " ".join(" ".join(parts).split())

    def _flush_line(self) -> None:
        value = self._clean(self._line_parts)
        if value:
            self.lines.append(value)
        self._line_parts = []


def parse_posting_html(content: str) -> tuple[list[str], list[str]]:
    parser = _PostingTextParser()
    parser.feed(content)
    return parser.lines, parser.requirements
