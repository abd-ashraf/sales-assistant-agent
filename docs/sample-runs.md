# Sample runs

The brief's three prompts, asked with `ask` on gpt-6.1-sol (the default) on 18 October 2026,
after `ingest` prepared the data on the same model. Each output is copied as the CLI printed
it: `→` lines are the tools the model called, `←` lines what each tool found, and the last
line counts the model calls and tokens for the question.

## 1. Product recommendation

```bash
uv run sales-assistant ask "We have Larox pressure filters but performance drops whenever our feed grade changes"
```

```text
  → search_product_docs(query='Filter optimizer changing feed process conditions existing Larox
pressure filters automatic setpoints cake moisture cycle time compatibility',
brochures=['filter-optimizer', 'larox-pf-brochure-b', 'larox-pf-brochure-a'])
    ← filter-optimizer p.2, filter-optimizer p.3, larox-pf-brochure-a p.1, larox-pf-brochure-b p.3,
larox-pf-brochure-b p.4

Metso Filter optimizer is the best option to investigate for your existing filters, rather than
starting with replacement equipment. Assuming the feed-grade changes also change slurry
characteristics, it addresses that variability by recalculating setpoints each cycle from cake
moisture and cycle time. [filter-optimizer p.2]

It adjusts feed amount, pressing delta-pressure and air-drying time, targeting consistent residual
moisture and optimized productivity under changing conditions. [filter-optimizer p.2–3]

Which Larox filter model do you have?
model calls: 2 · tokens: 5,669
```

One search covers the Filter optimizer and both Larox PF brochures. The answer recommends
the add-on for the filters the customer already has rather than new equipment, cites the
pages, and asks the one question that would sharpen it.

## 2. Service visit budget

```bash
uv run sales-assistant ask "A customer in Chile needs 12 filter cloths replaced on a Larox PF-DS tower press. What should I budget for the service visit?"
```

```text
  → estimate_service_cost(equipment='larox_pf_ds', job_type='filter_cloth_replacement',
country='Chile', parts=[{'name': 'filter cloth', 'quantity': 12}])
    ← FSR-0001, FSR-0014, FSR-0015, FSR-0027, FSR-0028, FSR-0031, FSR-0034, FSR-0035, FSR-0037,
FSR-0044

Budget USD 2,449, with a likely range of USD 1,759–3,072, for replacing 12 filter cloths on the
Larox PF-DS in Chile. This is a budget based on past visits, not a quote.

Typical breakdown:

 • Labour: USD 946
 • Travel: USD 645
 • 12 filter cloths: USD 858

The estimate uses replacement-job hours from six reports (FSR-0014, 0027, 0028, 0031, 0037, 0044),
Chile labour/travel records (FSR-0001, 0015, 0034, 0035), and cloth prices from FSR-0014, 0027 and
0031.

Assumptions and limits: planned weekday visit; VAT excluded; approximate 2024 exchange rates.
Weekend/emergency premiums are not covered, and the model does not increase site hours with cloth
quantity. One source report, FSR-0027, has inconsistent task-hour totals.
model calls: 2 · tokens: 4,579
```

Every figure comes from `estimate_service_cost`, which builds the budget in code from the
reports it lists. The answer says what the budget leaves out and warns about FSR-0027, whose
hours do not add up. `uv run sales-assistant estimate larox_pf_ds filter_cloth_replacement
Chile --part "filter cloth" --quantity 12` shows the tool's full text.

## 3. Flotation readings

```bash
uv run sales-assistant ask "The customer is getting 3.1% silica and 64.5% iron in their concentrate. They think that's normal. What do you think, and what could we suggest?"
```

```text
  → assess_flotation_readings(iron_pct=64.5, silica_pct=3.1)
    ← plant history, 4,097 hours
  → search_product_docs(query='CellStation air feed pulp level control existing flotation cells
upgrade', brochures=['cellstation'])
    ← cellstation p.1, cellstation p.2, cellstation p.3

I wouldn’t call those typical: they’re on the poorer side of our reference plant’s history—not
necessarily abnormal for this customer.

 • Silica 3.1%: reference median 2.00%; only 24% of hours were this high or higher.
 • Iron 64.5%: reference median 65.21%; only 28% of hours were this low or lower.
 • Both conditions occurred together in 20% of hours.

What to suggest: investigate air-feed and pulp-level stability first. In that history,
poorer-silica hours were associated with lower air flows and lower levels in several columns—not
proof that changing either will fix the grade.

CellStation is the best-fit option to explore, assuming air/level control needs improvement: it
controls flotation-cell air feed and pulp level, and its ExactLevel controller reduces disturbances
and stabilizes froth conditions. [cellstation p.1]

Caveat: this is one plant’s 2017 hourly history, with weak associations and month-to-month
variation—not a universal benchmark or a diagnosis.

What flotation equipment and air/level controls do they already have?
model calls: 3 · tokens: 8,277
```

Two tools: the plant comparison, then a brochure search for products that act on what it
found (air flow and pulp level). The shares are the tool's, the links are given as
associations with their limits, and the answer ends with a question about the customer's
current controls. `uv run sales-assistant assess 64.5 3.1` shows the tool's full text.
