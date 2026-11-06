#!/usr/bin/env python3
"""Assert assets/css/main.css still matches what assets/sass/ compiles to.

main.css is generated from assets/sass/main.scss, but it is committed and has
been hand-edited in the past. That is the hazard this guards: a hand-edit to
the CSS that never reaches the sass is silently destroyed the next time
anyone runs a compiler, and nothing else in the repo would notice.

Two assertions, both at the same seam - the stylesheet the browser is served:

  1. Every selector in main.css carries the same declarations as the sass
     compiles to, and no selector exists in one but not the other.
  2. main.css contains no CSS-only content - including rules parked inside
     comments - that the sass does not produce.

Formatting is deliberately NOT compared. The committed CSS was built by an
older compiler whose whitespace differs from current sass; that difference is
noise, not drift.

Run: python3 scripts/check-css-matches-sass.py
Needs a sass compiler (`npx sass`). Exits 2, not 0, if one is unavailable -
an unrunnable check is not a passing check.
"""
import re
import subprocess
import sys
import tempfile
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "assets" / "css" / "main.css"
SASS = ROOT / "assets" / "sass" / "main.scss"
SASS_VERSION = "sass@1.80.6"

COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
RULE_IN_TEXT = re.compile(r"([.#]?[A-Za-z][\w .:#>\[\]=\"'-]*)\s*\{")


def compile_sass() -> str | None:
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "out.css"
        try:
            r = subprocess.run(
                ["npx", "-y", SASS_VERSION, "--no-source-map", "--style=expanded",
                 str(SASS), str(out)],
                capture_output=True, text=True, timeout=300,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if not out.exists():
            print(r.stderr[-500:], file=sys.stderr)
            return None
        return out.read_text()


def normalise(decl: str) -> str:
    """Collapse layout and quote style - both are compiler formatting, not drift."""
    decl = re.sub(r"\s+", " ", decl).strip()
    return decl.replace("'", '"')


def rules(text: str) -> dict[str, list[str]]:
    """selector -> its declaration blocks in source order, @media included.

    Selectors inside an at-rule are keyed by their condition so a breakpoint
    override is never confused with the base rule of the same name.

    A selector can legitimately appear more than once at the same key - `body`
    does, four times - and the cascade means the later one only partly wins.
    So the value is a list in document order, not one block: keeping only the
    last would leave the earlier blocks uncompared, and drift in them unseen.
    """
    text = COMMENT.sub("", text)
    found: dict[str, list[str]] = {}

    def walk(body: str, prefix: str) -> None:
        i = 0
        while True:
            brace = body.find("{", i)
            if brace == -1:
                return
            head = body[i:brace].strip()
            depth, j = 1, brace + 1
            while j < len(body) and depth:
                depth += (body[j] == "{") - (body[j] == "}")
                j += 1
            inner = body[brace + 1:j - 1]
            if head.startswith("@"):
                walk(inner, f"{prefix}{re.sub(r'\s+', ' ', head)} | ")
            elif head:
                decls = ";".join(sorted(
                    normalise(d) for d in inner.split(";") if d.strip()
                ))
                for s in (x.strip() for x in head.split(",")):
                    if s:
                        found.setdefault(prefix + re.sub(r"\s+", " ", s), []).append(decls)
            i = j

    walk(text, "")
    return found


def main() -> int:
    compiled = compile_sass()
    if compiled is None:
        print("CANNOT RUN - no sass compiler available (`npx sass` failed).")
        print("This check is unrunnable, which is not the same as passing.")
        return 2

    css_text = CSS.read_text()
    a, b = rules(css_text), rules(compiled)
    failures = []

    only_css = sorted(set(a) - set(b))
    only_sass = sorted(set(b) - set(a))
    changed = sorted(s for s in set(a) & set(b) if a[s] != b[s])

    for s in only_css:
        failures.append(f"selector only in main.css, not produced by the sass: {s}")
    for s in only_sass:
        failures.append(f"selector produced by the sass but missing from main.css: {s}")
    for s in changed:
        failures.append(
            f"declarations differ for {s}"
            f"\n      css:  {' || '.join(a[s])[:200]}"
            f"\n      sass: {' || '.join(b[s])[:200]}")

    # CSS-only content parked inside comments - invisible to the selector
    # comparison above, and exactly what a recompile would destroy.
    sass_text = SASS.read_text()
    for block in COMMENT.findall(css_text):
        for sel in RULE_IN_TEXT.findall(block):
            sel = sel.strip()
            if sel and sel not in sass_text and sel not in compiled:
                failures.append(
                    f"commented-out rule in main.css that the sass does not have: {sel!r} "
                    "- a recompile would destroy it")

    print(f"  selectors in main.css        {len(a)}")
    print(f"  selectors compiled from sass {len(b)}")

    if failures:
        print("\nFAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS")
    return 0


def _self_test() -> None:
    """One assertion, for the one thing in here that is not a straight read.

    A selector repeated at the same key must keep both blocks: this returned
    only `color: blue` until it didn't, and nothing in main.css would have
    shown it - the duplicate `body` rules happened to agree on both sides.
    """
    assert rules("a { color: red; } a { color: blue; }") == {
        "a": ["color: red", "color: blue"]}


if __name__ == "__main__":
    _self_test()
    sys.exit(main())
