"""The screen, as a tree.

``uiautomator dump`` returns what is actually rendered: every visible node
with its text, its identifiers and its pixel bounds. Reading it is looking at
the screen — the same information a person sees, in the same layout — and the
bounds it gives are what make a tap land on the thing you looked at.

This module is deliberately ignorant of any particular app. It parses the
dump, finds nodes by what is on them, and hands back coordinates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence
from xml.etree import ElementTree

BOUNDS = re.compile(r"^\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]$")


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0


def parse_bounds(raw: str) -> Bounds:
    match = BOUNDS.match((raw or "").strip())
    if not match:
        return Bounds(0, 0, 0, 0)
    left, top, right, bottom = (int(part) for part in match.groups())
    return Bounds(left, top, right, bottom)


@dataclass
class UiNode:
    """One rendered node."""

    cls: str = ""
    package: str = ""
    resource_id: str = ""
    text: str = ""
    content_desc: str = ""
    bounds: Bounds = field(default_factory=lambda: Bounds(0, 0, 0, 0))
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    scrollable: bool = False
    depth: int = 0
    order: int = 0
    children: List["UiNode"] = field(default_factory=list)
    # The ancestor that would receive a tap on this node. Excluded from repr
    # and equality: it points back up the tree.
    clickable_host: Optional["UiNode"] = field(default=None, repr=False, compare=False)

    @property
    def center(self) -> tuple[int, int]:
        return self.bounds.center

    @property
    def label(self) -> str:
        """What a person would read off this node."""
        return self.text or self.content_desc

    def walk(self) -> Iterator["UiNode"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def nearest_clickable(self) -> "UiNode":
        """This node if it takes taps, else the closest ancestor that does.

        Text labels are usually not themselves clickable; the row containing
        them is. Resolved during parsing, so every node knows its own answer.
        """
        return self.clickable_host or self


def _flag(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() == "true"


def parse_ui_dump(xml: str) -> Optional[UiNode]:
    """Parse a ``uiautomator dump``. Returns None if there is no tree in it.

    adb output often carries a trailing line such as ``UI hierchary dumped to:
    ...``; leading or trailing noise is tolerated rather than fatal, because a
    screen read failing silently is worse than one that recovers.
    """
    if not xml:
        return None
    start = xml.find("<hierarchy")
    if start < 0:
        start = xml.find("<?xml")
        if start < 0:
            return None
    end = xml.rfind("</hierarchy>")
    body = xml[start : end + len("</hierarchy>")] if end > start else xml[start:]
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None

    counter = [0]

    def build(element, depth: int, clickable_host: Optional[UiNode]) -> UiNode:
        node = UiNode(
            cls=element.get("class", ""),
            package=element.get("package", ""),
            resource_id=element.get("resource-id", ""),
            text=element.get("text", ""),
            content_desc=element.get("content-desc", ""),
            bounds=parse_bounds(element.get("bounds", "")),
            clickable=_flag(element.get("clickable")),
            enabled=_flag(element.get("enabled")) or element.get("enabled") is None,
            focused=_flag(element.get("focused")),
            scrollable=_flag(element.get("scrollable")),
            depth=depth,
        )
        node.order = counter[0]
        counter[0] += 1
        node.clickable_host = node if node.clickable else clickable_host
        for child in list(element):
            node.children.append(build(child, depth + 1, node.clickable_host))
        return node

    if root.tag == "hierarchy":
        children = list(root)
        if not children:
            return None
        if len(children) == 1:
            return build(children[0], 0, None)
        # More than one window in the dump: keep them under a synthetic root
        # so nothing on screen is dropped.
        holder = UiNode(
            cls="hierarchy", bounds=parse_bounds(children[0].get("bounds", ""))
        )
        for child in children:
            holder.children.append(build(child, 1, None))
        return holder
    return build(root, 0, None)


@dataclass(frozen=True)
class Selector:
    """How to recognise something on screen.

    Every supplied field must match. ``resource_id`` and ``cls`` match on a
    suffix so a map can say ``compose_message_text`` without repeating the
    package, and ``*_contains`` matches are case-insensitive because app
    copy changes case between versions far more often than it changes words.
    """

    resource_id: str = ""
    text: str = ""
    text_contains: str = ""
    content_desc: str = ""
    content_desc_contains: str = ""
    cls: str = ""
    clickable: Optional[bool] = None
    scrollable: Optional[bool] = None
    package: str = ""

    def describe(self) -> str:
        parts = [
            f"{name}={value!r}"
            for name, value in (
                ("resource_id", self.resource_id),
                ("text", self.text),
                ("text_contains", self.text_contains),
                ("content_desc", self.content_desc),
                ("content_desc_contains", self.content_desc_contains),
                ("cls", self.cls),
                ("package", self.package),
            )
            if value
        ]
        for name, value in (
            ("clickable", self.clickable),
            ("scrollable", self.scrollable),
        ):
            if value is not None:
                parts.append(f"{name}={value}")
        return " ".join(parts) or "<empty selector>"

    def is_empty(self) -> bool:
        return self.describe() == "<empty selector>"

    def matches(self, node: UiNode) -> bool:
        if self.resource_id and not _id_matches(node.resource_id, self.resource_id):
            return False
        if self.cls and not (node.cls == self.cls or node.cls.endswith("." + self.cls)):
            return False
        if self.package and node.package != self.package:
            return False
        if self.text and node.text != self.text:
            return False
        if self.text_contains and self.text_contains.lower() not in node.text.lower():
            return False
        if self.content_desc and node.content_desc != self.content_desc:
            return False
        if (
            self.content_desc_contains
            and self.content_desc_contains.lower() not in node.content_desc.lower()
        ):
            return False
        if self.clickable is not None and node.clickable is not self.clickable:
            return False
        if self.scrollable is not None and node.scrollable is not self.scrollable:
            return False
        return True

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Selector":
        known = {
            "resource_id",
            "text",
            "text_contains",
            "content_desc",
            "content_desc_contains",
            "cls",
            "clickable",
            "scrollable",
            "package",
        }
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"Unknown selector field(s): {', '.join(sorted(unknown))}. "
                f"Known fields: {', '.join(sorted(known))}"
            )
        return cls(
            resource_id=str(data.get("resource_id", "")),
            text=str(data.get("text", "")),
            text_contains=str(data.get("text_contains", "")),
            content_desc=str(data.get("content_desc", "")),
            content_desc_contains=str(data.get("content_desc_contains", "")),
            cls=str(data.get("cls", "")),
            clickable=data.get("clickable")
            if isinstance(data.get("clickable"), bool)
            else None,
            scrollable=(
                data.get("scrollable")
                if isinstance(data.get("scrollable"), bool)
                else None
            ),
            package=str(data.get("package", "")),
        )


def _id_matches(actual: str, wanted: str) -> bool:
    if not actual:
        return False
    if actual == wanted:
        return True
    return actual.endswith(":id/" + wanted) or actual.endswith("/" + wanted)


def find_all(
    root: Optional[UiNode], *selectors: Selector, visible_only: bool = True
) -> List[UiNode]:
    """Every node matching any of the selectors, in reading order.

    Several selectors act as alternatives, which is how an App Map carries a
    fallback for an app version that renamed a view.
    """
    if root is None or not selectors:
        return []
    found = [
        node
        for node in root.walk()
        if any(selector.matches(node) for selector in selectors)
        and not (visible_only and node.bounds.is_empty())
    ]
    return sorted(found, key=lambda node: node.order)


def find(
    root: Optional[UiNode], *selectors: Selector, visible_only: bool = True
) -> Optional[UiNode]:
    matches = find_all(root, *selectors, visible_only=visible_only)
    return matches[0] if matches else None


def texts(nodes: Sequence[UiNode]) -> List[str]:
    return [node.label for node in nodes if node.label]


__all__ = [
    "Bounds",
    "UiNode",
    "Selector",
    "parse_bounds",
    "parse_ui_dump",
    "find",
    "find_all",
    "texts",
]
