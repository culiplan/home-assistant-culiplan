"""Static guards on the sidebar panel's stylesheet (custom panel height).

The panel is registered with ``component_name="custom"`` and
``embed_iframe: False``. HA does not give ``<ha-panel-custom>`` a definite
height in that configuration, so a percentage height on ``:host`` resolves to
``auto``: the host shrinks to content height and the iframe collapses with it.
A reporter measured the whole chain at 1344x150 in a 1600x1000 viewport —
nav bar, one card, then empty page background for the rest of the screen.

The fix is a viewport-relative height. These tests parse the stylesheet text
rather than render it; they exist to stop ``height: 100%`` from creeping back
onto ``:host``, which is the exact regression that produced the collapse.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PANEL_JS = (
    Path(__file__).resolve().parents[1]
    / "custom_components/culiplan/frontend/culiplan-panel.js"
)


@pytest.fixture(scope="module")
def styles() -> str:
    """Return the STYLES template literal, comments stripped."""
    source = PANEL_JS.read_text(encoding="utf-8")
    start = source.index("const STYLES = `")
    end = source.index("`;", start)
    css = source[start + len("const STYLES = `") : end]
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _rule(styles: str, selector: str) -> str:
    """Return the declaration block for a top-level selector."""
    match = re.search(
        rf"(?:^|\}}|\n)\s*{re.escape(selector)}\s*\{{(.*?)\}}", styles, re.DOTALL
    )
    assert match, f"{selector} rule not found"
    return match.group(1)


def test_host_height_is_viewport_relative(styles: str) -> None:
    """:host must not depend on an ancestor's height."""
    host = _rule(styles, ":host")
    heights = re.findall(r"height:\s*([^;]+);", host)
    assert heights, ":host declares no height"
    for value in heights:
        assert "%" not in value, (
            f":host height {value.strip()!r} is ancestor-relative; HA gives "
            "<ha-panel-custom> no definite height, so this resolves to auto and "
            "the panel collapses to content height (~150px)."
        )
    assert any("vh" in v for v in heights), ":host needs a vh-based height"


def test_host_is_a_flex_column(styles: str) -> None:
    """The iframe grows via flex, so the host must establish the column."""
    host = _rule(styles, ":host")
    assert re.search(r"display:\s*flex", host), ":host must be display: flex"
    assert re.search(r"flex-direction:\s*column", host)


def test_fill_grows_to_consume_remaining_space(styles: str) -> None:
    """.fill is the iframe — it must flex, not inherit a percentage height."""
    fill = _rule(styles, ".fill")
    assert re.search(r"flex:\s*1", fill), ".fill must grow to fill the host"
    assert not re.search(r"height:\s*\d+%", fill), (
        ".fill must not use a percentage height — it collapses with the host"
    )
    assert re.search(r"min-height:\s*0", fill), (
        ".fill needs min-height: 0 so the flex item can shrink below content size"
    )


def test_layout_chain_from_host_to_iframe_is_unbroken(styles: str) -> None:
    """Every element between :host and the iframe must grow.

    This is the failure 0.14.2 shipped: :host was fixed to 100dvh, but the
    render path wraps content in <div class="culiplan-body">, which had no
    stylesheet rule at all — just a block box with an inline height. That
    broke the chain, so .fill's ``flex: 1`` had no flex container to act in,
    the iframe resolved to no height, and it fell back to the HTML default
    iframe box of 150px. Same symptom, one level down.

    Testing :host and .fill in isolation missed it. The chain is the invariant.
    """
    source = PANEL_JS.read_text(encoding="utf-8")

    # Discover wrapper classes the render path actually creates, so a NEW
    # wrapper added later cannot silently break the chain either.
    wrappers = set(re.findall(r'\.className\s*=\s*"([a-z-]+)"', source))
    wrappers &= {"culiplan-body"} | {w for w in wrappers if w.endswith("-body")}
    assert "culiplan-body" in wrappers, "render path no longer creates .culiplan-body"

    for cls in sorted(wrappers):
        rule = _rule(styles, f".{cls}")
        assert re.search(r"flex:\s*1", rule), f".{cls} must grow to fill its parent"
        assert re.search(r"display:\s*flex", rule), (
            f".{cls} wraps the iframe, so it must be a flex container — "
            "otherwise the child's flex sizing is inert"
        )
        assert re.search(r"min-height:\s*0", rule), f".{cls} needs min-height: 0"


def test_layout_is_not_set_from_javascript(styles: str) -> None:
    """No inline height assignments — layout lives in STYLES.

    ``body.style.height = "100%"`` competed with the flex sizing and hid the
    broken chain behind a value that looked correct.
    """
    source = PANEL_JS.read_text(encoding="utf-8")
    assert not re.search(r"\.style\.height\s*=", source), (
        "set height in the STYLES stylesheet, not inline from JS"
    )


def test_iframe_can_never_fall_back_to_the_default_box(styles: str) -> None:
    """An iframe with no resolved height renders at 150px, not 0.

    That default is why the collapse looked like a deliberate short panel
    rather than a missing element, in both 0.14.1 and 0.14.2.
    """
    fill = _rule(styles, ".fill")
    grows = re.search(r"flex:\s*1", fill)
    has_height = re.search(r"height:\s*(100%|100[vd]h)", fill)
    assert grows or has_height, (
        ".fill must either flex-grow inside a flex parent or carry an explicit "
        "height; with neither, the iframe falls back to 150px"
    )


def test_dynamic_viewport_height_is_offered(styles: str) -> None:
    """100dvh keeps mobile browser chrome from clipping the app."""
    host = _rule(styles, ":host")
    assert "100dvh" in host
    # Must come after the 100vh fallback so older browsers keep a usable value.
    assert host.index("100vh") < host.index("100dvh")


# ─── Theme bridge (0.16.1) ──────────────────────────────────────────────────


def _method(source: str, name: str) -> str:
    """Return the body of a class method (up to the next method)."""
    start = source.index(f"  {name}(")
    nxt = re.search(r"\n  (?:async )?_?[a-zA-Z]+\([^)]*\) \{", source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


def test_theme_tokens_are_resolved_not_raw() -> None:
    """Custom themes declare tokens as var()/hsl()/color-mix().

    Posting the raw ``getPropertyValue`` text left the cross-origin app with
    values it cannot resolve (e.g. ``var(--ctp-blue)``). Each token must go
    through a probe element so the app receives a computed colour.
    """
    source = PANEL_JS.read_text(encoding="utf-8")
    resolve = _method(source, "_resolveThemeTokens")
    assert "getComputedStyle(probe)" in resolve
    assert "`var(${name})`" in resolve
    assert "THEME_PROBE_SENTINEL" in resolve, (
        "tokens that are not a colour (gradients, images) must be detected and omitted"
    )
    assert ".remove()" in resolve, "the probe must not stay in HA's DOM"
    post = _method(source, "_postThemeTokens")
    assert "_resolveThemeTokens()" in post
    assert "getPropertyValue" not in post


def test_theme_payload_carries_dark_mode_and_theme_name() -> None:
    source = PANEL_JS.read_text(encoding="utf-8")
    post = _method(source, "_postThemeTokens")
    assert "darkMode: !!themes.darkMode" in post
    assert "themeName:" in post
    assert "CULIPLAN_ORIGIN" in post, "never post theme data to '*'"


def test_unchanged_theme_payloads_are_skipped_but_reload_forces() -> None:
    source = PANEL_JS.read_text(encoding="utf-8")
    post = _method(source, "_postThemeTokens")
    assert "_lastThemePayload" in post
    assert "this._postThemeTokens(iframe, true)" in source, (
        "a fresh iframe load must always get the theme, even if unchanged"
    )
