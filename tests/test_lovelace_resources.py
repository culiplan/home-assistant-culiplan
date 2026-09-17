"""
Static checks on the Lovelace resource declaration (task-1408).

AC coverage:
  AC#1 — _LOVELACE_RESOURCES lists all 3 card .js files, self-served
  AC#2 — idempotency across reloads
  AC#3 — unload choice documented: resources NOT removed (see __init__ comment)
  AC#4 — manual fallback path still works

Only AC#1 is checked here, by parsing the declaration out of the source with
AST — no import, no HA runtime.

AC#2 and AC#4 are BEHAVIOURAL and live in tests/test_init_misc.py, where they
call the real ``_async_register_lovelace_resources`` against
``_FakeResourceCollection`` (which mirrors HA's actual
``ResourceStorageCollection`` API).

This file used to carry those behavioural tests too, but written against an
inline re-implementation of the function plus an ``AsyncMock`` collection. That
mock accepted ``await async_items()`` and ``async_load(True)``, neither of which
the real HA API supports — so the tests passed green while the shipped code
failed both calls, fell into a bare ``except``, and re-registered every resource
on each startup. Never assert against a copy of the logic; call the function.
"""

from __future__ import annotations

import ast
from pathlib import Path

INIT_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components/culiplan/__init__.py"
)


def _parse_lovelace_resources(source: str) -> list[dict]:
    """Extract _LOVELACE_RESOURCES entries from source using AST.

    Handles both plain assignment (ast.Assign) and annotated assignment
    (ast.AnnAssign, i.e. `_LOVELACE_RESOURCES: tuple[...] = (...)`).
    """
    tree = ast.parse(source)
    results: list[dict] = []

    for node in ast.walk(tree):
        value_node = None

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_LOVELACE_RESOURCES":
                    value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "_LOVELACE_RESOURCES"
            ):
                value_node = node.value

        if value_node is not None and isinstance(value_node, (ast.Tuple, ast.List)):
            for elt in value_node.elts:
                if isinstance(elt, ast.Dict):
                    entry: dict = {}
                    for k, v in zip(elt.keys, elt.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            entry[k.value] = v.value
                    results.append(entry)

    return results


class TestLovelaceResourcesConstant:
    def _get_resources(self) -> list[dict]:
        resources = _parse_lovelace_resources(INIT_PATH.read_text(encoding="utf-8"))
        assert resources, "_LOVELACE_RESOURCES constant not found in __init__.py"
        return resources

    def test_lists_three_cards(self) -> None:
        resources = self._get_resources()
        assert len(resources) == 3, f"Expected 3 resources, found {len(resources)}"

    def test_contains_all_three_card_urls(self) -> None:
        urls = [r["url"] for r in self._get_resources()]
        for name in ("kitchen-dashboard.js", "pantry-tracker.js", "cooking-mode.js"):
            assert any(name in u for u in urls), f"{name} not in resources"

    def test_all_resources_are_modules(self) -> None:
        for r in self._get_resources():
            assert r.get("res_type") == "module", (
                f"Expected res_type='module', got {r.get('res_type')!r} for {r.get('url')}"
            )

    def test_urls_are_served_by_the_integration(self) -> None:
        """Cards must come from our own static path, not /hacsfiles/.

        /hacsfiles/<name>/ is populated only for HACS *plugin* repos. This is a
        HACS *integration*: HACS copies custom_components/culiplan/ and nothing
        else, so /hacsfiles/culiplan/... never existed and every card request
        404'd. /culiplan_static/ is registered by the integration itself.
        """
        for r in self._get_resources():
            assert r["url"].startswith("/culiplan_static/cards/"), r["url"]
            assert "hacsfiles" not in r["url"], r["url"]

    def test_urls_carry_no_cache_busting_query(self) -> None:
        """A versioned URL would orphan the previous row on every upgrade.

        The static path is registered with cache_headers=False, so there is
        nothing to bust.
        """
        for r in self._get_resources():
            assert "?" not in r["url"], r["url"]

    def test_bundles_exist_in_the_shipped_package(self) -> None:
        """Each registered URL must resolve to a file inside the integration."""
        frontend = INIT_PATH.parent / "frontend"
        for r in self._get_resources():
            rel = r["url"].removeprefix("/culiplan_static/")
            assert (frontend / rel).is_file(), f"missing bundle for {r['url']}"
