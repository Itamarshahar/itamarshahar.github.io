#!/usr/bin/env python3
"""Assert the page entrance stays snappy.

This is the only screen on the site and the sequence gates every link on it,
so the whole entrance must settle well inside a second. The template shipped
at 3.75s; regressing there makes the page feel like it is buffering.

Run: python3 scripts/check-entrance-timing.py
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


def main() -> int:
    css = CSS.read_text()
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
    raw_easing = len(re.findall(r"cubic-bezier\(", SASS.read_text()))
    if raw_easing:
        failures.append(
            f"{raw_easing} raw cubic-bezier literal(s) in assets/sass/main.scss - "
            "use _easing() so the curve is defined once in _vars.scss")

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
    sys.exit(main())
