"""Smoke test for the SPA (assets/app.js).

The SPA has no build step and no browser in CI, so the cheap-but-real check is
to evaluate ``app.js`` in a Node sandbox with a stubbed DOM and assert that every
view function ``route()`` dispatches to is actually reachable at global scope.

This catches the regression class where a bad merge nests ``viewAgents`` /
``viewAbout`` inside another function: the file still parses
(braces balance) but the tabs throw ``ReferenceError`` at runtime.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_APP_JS = _ROOT / "assets" / "app.js"

# Views that route() switches on; each must be a global function.
_REQUIRED_GLOBALS = [
    "viewHome",
    "viewProfile",
    "viewThread",
    "viewExplore",
    "viewTag",
    "viewNotifications",
    "viewFollowList",
    "viewBookmarks",
    "viewMessages",
    "viewConversation",
    "viewAgents",
    "viewAbout",
    "viewNotFound",
    "route",
    "refreshContext",
]

_CHECK_JS = """
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const noop = () => {};
const el = {
  innerHTML: "", className: "", textContent: "", value: "", hidden: false, dataset: {},
  style: {}, scrollTop: 0, scrollHeight: 0,
  addEventListener: noop, removeEventListener: noop, focus: noop, remove: noop,
  setAttribute: noop, getAttribute: () => null,
  querySelector: () => el, querySelectorAll: () => [], closest: () => null,
  classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
  insertAdjacentHTML: noop,
};
const sandbox = {
  console,
  localStorage: { getItem: () => "dark", setItem: noop },
  document: {
    documentElement: { setAttribute: noop },
    getElementById: () => el, querySelector: () => el, querySelectorAll: () => [],
    addEventListener: noop, createElement: () => el,
  },
  window: { location: { hash: "#/home" }, addEventListener: noop, history: { length: 1, back: noop } },
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  setTimeout: () => 0, clearTimeout: noop, confirm: () => true,
  URLSearchParams, encodeURIComponent,
};
sandbox.globalThis = sandbox;
vm.runInContext(src, vm.createContext(sandbox), { filename: "app.js" });
const required = JSON.parse(process.argv[2]);
const missing = required.filter((n) => typeof sandbox[n] !== "function");
process.stdout.write(JSON.stringify({ missing }));
"""


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class SpaSmokeTest(unittest.TestCase):
    def test_view_functions_are_globally_reachable(self):
        proc = subprocess.run(
            ["node", "-e", _CHECK_JS, str(_APP_JS), json.dumps(_REQUIRED_GLOBALS)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(
            result["missing"],
            [],
            f"SPA functions not reachable at global scope (nested by mistake?): {result['missing']}",
        )

    def test_route_dispatches_only_known_views(self):
        source = _APP_JS.read_text(encoding="utf-8")
        # Every `case "x": return await viewFoo(...)` target must be one of ours.
        import re

        targets = set(re.findall(r"await\s+(view[A-Za-z]+)\(", source))
        self.assertTrue(targets, "expected route() to call view functions")
        self.assertTrue(targets.issubset(set(_REQUIRED_GLOBALS)), sorted(targets))


if __name__ == "__main__":
    unittest.main()
