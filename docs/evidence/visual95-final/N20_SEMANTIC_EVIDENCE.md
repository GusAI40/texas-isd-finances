# N20 answer-to-evidence check

Captured from frozen runtime source with recorded public GET fixtures, including `/health`, and a mocked `/query`. No provider call was made.

- The landing journey shows the visitor's question, four separate TEA PEIMS record groups, the matched district ID `057905`, the resulting quantitative answer, and a visible `/sources` link in one connected workflow.
- The landing composition marks encode the verified Dallas ISD fiscal 2025 all-funds partition: classroom `32.9%`, construction `23.1%`, debt `15.1%`, and other combined `28.9%`. Their exact records total `$3,319,208,715`.
- The supported chat repeats the visitor's actual question and identifies `Dallas ISD / Fiscal 2025 / All funds`. Its four bars are max-scaled reported-dollar comparisons: `$1,092,607,589`, `$766,316,261`, `$500,174,938`, and `$960,109,927`; the largest record is 100%, so the chart does not imply an arbitrary denominator.
- The supported answer visibly names `TEA PEIMS actual finance`, links to `/sources`, and states `Historical records, not a live budget.`
- `n20-semantic-evidence.json` records the rendered labels, dollar values, mark widths, source link, document geometry, fixture requests, source hashes, and PNG hashes.

The supported-chat PNG uses an evidence-only browser stylesheet to expose the complete normally scrollable answer in one image. Runtime source was not changed.
