# Graph Insights — The District Network Analyzed

Produced by `scripts/graph_insights.py` (deterministic; rerun after each
TEA refresh). The district similarity graph itself is built by
`scripts/build_similarity_graph.py` — see the "why exogenous features"
rationale there.

## 1. Flag co-occurrence network (20,587 district-years)

Which anomaly types travel together, measured as lift over independence:

| Flag pair | Joint events | Lift | Reading |
|---|---|---|---|
| revenue_drop + enrollment_decline | 156 | **6.1×** | The headline: money follows students. A district losing >10% enrollment is 6× likelier to also take a >15% revenue hit the same year. Early-warning implication: enrollment decline is the leading indicator worth watching. |
| spend_spike + per_student_spike | 577 | 5.4× | Largely mechanical — a spending jump with flat enrollment necessarily moves per-student spend. |
| per_student_spike + enrollment_decline | 441 | 3.1× | The denominator effect: shrinking districts look like "big spenders" per student by division alone. This is why the dashboard's flag cards warn about it. |
| revenue_drop + spend_spike | 41 | 2.2× | Rare but interesting: spending up while revenue falls — the pattern most worth a board question. |
| revenue_drop + per_student_spike | 184 | 1.5× | Weak association. |
| spend_spike + enrollment_decline | 3 | 0.1× | Anti-correlated by construction (the spend-spike flag requires flat enrollment). Good validity check on the flag definitions. |

## 2. The statewide similarity map

`static/map_data.json` → rendered at `/map`. Every district plotted by PCA
of the exogenous feature space (log enrollment, 5-yr growth,
revenue/student, local-tax share). PC1+PC2 capture **70%** of variance:
PC1 reads roughly as *scale + local wealth*, PC2 as *growth trajectory*.
Nearby dots = structurally similar districts; color = spending per student,
so spending patterns can be *seen against* structure rather than mixed
into it.

## 3. Temporal drift (2015 → 2025)

Distance each district moved in state-relative feature space over a
decade. The top movers are almost all **very small districts and
charters** with extreme enrollment swings (e.g., Divide ISD growth-z
+5.7) — small-N volatility, not policy stories. Honest conclusion: drift
is a cleaning tool (it flags unstable entities to treat carefully in
comparisons), not yet a headline feature. A size-weighted version would
be needed to surface meaningful mid/large-district transitions.

## 4. Turnaround detection (live feature)

`GET /district/{id}/turnarounds` walks the similarity graph and scans
each structural peer's 17-year history for reversal patterns:

- **Deficit reversal:** ≥2 consecutive years spending > revenue, followed
  by ≥2 consecutive surplus years.
- **Enrollment reversal:** ≥3 consecutive decline years followed by ≥2
  growth years.

Shown on the dashboard as "districts like yours that turned it around" —
the graph turning benchmarking into *hope with receipts*.
