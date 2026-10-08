# Public visual design contract

The report leads with district selection, then a compact statewide spending mark
and district-specific charts. A number is always paired with its unit, period,
status, and source affordance. Finance FY2025 and outcomes FY2024 remain visibly
different vintages. Missing is never drawn as zero; modeled is named in text and
uses a distinct caption.

The design uses the existing paper/ink palette, single blue accent, native SVG,
Canvas, and HTML tables. It adds no vendor, font, framework, CDN, animation
dependency, or production build. Charts retain their table alternatives. At
390px, 320px reflow, 200% zoom, and reduced motion, controls remain usable and
only individual table/chart scroll areas may scroll horizontally.

## Ratio rubric

For every analytic state and viewport, the harness records tight content bounds.
`visual` means a data-bearing SVG/Canvas mark or a compact labeled numeric card.
`prose` means a standalone narrative paragraph, including narrative inside a
card. Navigation, form controls, footer/legal content, expanded sources, and
accessible table alternatives are itemized exclusions. Overlap is invalid;
narrative overlapping a visual has prose precedence. Both the initial analytic
viewport and full default report must independently satisfy `V/(V+P) >= .95`
and `P/(V+P) <= .05`. This is a presentation target, not an accuracy or
usability claim. Screenshots require independent semantic classification review;
agent inspection is identified separately from a human participant study.

## Retention model

For a hypothetical district cohort of ten teachers, annual exposure periods are
K, 1, 2, 3, 4, and 5. `10 × (1 − turnover/100)^6` is rounded only for the
headline. It assumes constant annual turnover and equal retention probability;
it is not building-level tracking or a forecast for particular teachers.
