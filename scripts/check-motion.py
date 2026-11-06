#!/usr/bin/env python3
"""Assert the page's motion stays correct and snappy.

This is the only screen on the site and the entrance gates every link on it,
so the whole sequence must settle well inside a second. The template shipped
at 3.75s; regressing there makes the page feel like it is buffering.

Beyond the budget it guards the three properties that are easy to undo by
accident and invisible in review: press and hover must move the compositor
rather than the layout, hover must not fire on touch, and reduced motion must
still deliver the content.

Run:  python3 scripts/check-motion.py [main.css] [main.scss]

The optional paths exist so every assertion can be mutation-tested - pointed
at a deliberately broken copy to prove it actually fails. An assertion never
seen to fail is not a test, and one that cannot be reached by any mutation is
dead code wearing a test's clothes.
"""
import re
import sys
import pathlib

BUDGET_MS = 750
ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "assets" / "css" / "main.css"
SASS = ROOT / "assets" / "sass" / "main.scss"


def ms(value: str) -> float:
    value = value.strip()
    return float(value[:-2]) if value.endswith("ms") else float(value[:-1]) * 1000


def main(css_path: pathlib.Path = CSS, sass_path: pathlib.Path = SASS) -> int:
    css = css_path.read_text()
    failures = []

    # Unprefixed `animation: <name> <duration> [delay] ...` shorthands.
    settle = {}
    for name, rest in re.findall(r"\n\t*animation: ([a-z-]+) ([^;]+);", css):
        times = re.findall(r"(\d*\.?\d+m?s)", rest)
        if not times or name == "bg":  # bg is an infinite ambient pan, not entrance
            continue
        duration = ms(times[0])
        delay = ms(times[1]) if len(times) > 1 else 0.0
        settle[name] = max(settle.get(name, 0.0), duration + delay)

    # Per-item nav stagger lives in separate animation-delay rules.
    nav_duration = settle.get("nav-icons", 0.0)
    delays = [ms(d) for d in re.findall(r"\n\t*animation-delay: (\d*\.?\d+m?s);", css)]
    nav_delays = [d for d in delays if d > 0]
    if nav_duration and nav_delays:
        # Only the first four slots are used - the markup has four nav links.
        settle["nav-icons"] = nav_duration + max(sorted(nav_delays)[:4])

    if not settle:
        failures.append("found no entrance animations in main.css - did the selectors change?")

    total = max(settle.values()) if settle else 0.0
    if total > BUDGET_MS:
        failures.append(f"entrance settles at {total:.0f}ms, over the {BUDGET_MS}ms budget")

    if "prefers-reduced-motion" not in css:
        failures.append("no prefers-reduced-motion block - the 60s background pan has no opt-out")

    if "is-preload" in css:
        failures.append("is-preload gate is back - it defers all motion until every image and font loads")

    if re.search(r"#header nav a:(hover|active) \{\n\t*font-size:", css):
        failures.append("nav hover/press animates font-size - reflows the nav row every frame; use transform")

    # The compiled CSS repeats the easing at every site - that is just what a
    # compiler does. The source must not: this repo keeps shared values in
    # _vars.scss behind an accessor (_duration, _palette, _size ...).
    raw_easing = len(re.findall(r"cubic-bezier\(", sass_path.read_text()))
    if raw_easing:
        failures.append(
            f"{raw_easing} raw cubic-bezier literal(s) in assets/sass/main.scss - "
            "use _easing() so the curve is defined once in _vars.scss")

    # --- Row 2: hover moves the compositor, and never fires on touch ---------
    if not re.search(r"#header nav a:hover:before \{[^}]*transform: scale\(", css):
        failures.append(
            "nav hover does not scale via transform - the hover grow must be a "
            "transform on the ::before, not a size change that reflows the row")
    if not re.search(r"\(hover: hover\) and \(pointer: fine\)", css):
        failures.append(
            "hover styles are not gated behind (hover: hover) and (pointer: fine) - "
            "they will fire on touch, where there is no hover to leave")
    if re.search(r"#header nav a:before \{[^}]*transition: all", css):
        failures.append(
            "nav transition uses `all` - name the properties, or every future "
            "property added to this rule silently animates too")

    # --- Row 3: press feedback ------------------------------------------------
    if not re.search(r"#header nav a:active:before \{[^}]*transform: scale\(0\.97\)", css):
        failures.append(
            "press feedback is not transform: scale(0.97) on the ::before - the "
            "Resume link opens a PDF in a new tab and the press must register first")
    if not re.search(r"#header nav a:active:before \{[^}]*transition-duration: 0\.16s", css):
        failures.append("press feedback is not 160ms")

    # --- Row 4: reduced motion still delivers the content ---------------------
    rm = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\t\}", css, re.DOTALL)
    if rm:
        block = rm.group(1)
        if not re.search(r"#bg \{[^}]*animation: none", block):
            failures.append(
                "reduced motion does not stop #bg - a 60s infinite pan with no "
                "opt-out is the one real accessibility defect on this page")
        if "animation-fill-mode: forwards" not in block:
            failures.append(
                "reduced motion removes the entrance without animation-fill-mode: "
                "forwards - content would never arrive at its settled state and "
                "the page would render empty. Gentler, not zero.")

    for name, t in sorted(settle.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<12} settles at {t:>6.0f}ms")
    print(f"  {'TOTAL':<12} {total:>13.0f}ms  (budget {BUDGET_MS}ms)")

    if failures:
        print("\nFAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(
        pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else CSS,
        pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else SASS,
    ))
