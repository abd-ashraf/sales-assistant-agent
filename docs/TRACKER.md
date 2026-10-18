# Tracker

The plan this assistant was built to, one step per commit. Each box is ticked in the
commit that completes it.

## Goal

A command-line assistant for a Metso salesperson on a call with a mining customer. For
each message it decides for itself whether to answer, ask one short question, or use a
tool, and it says so when the answer is not in its data.

- **Products:** answer questions and recommend a product, from the brochures only.
- **Service costs:** estimate a field service visit, from past service reports only.
- **Flotation (optional part):** judge concentrate readings against plant history.

## Approach

- **Agent:** a LangGraph graph with two steps in a loop. The model step answers, asks,
  or requests a tool; the tool step runs it and hands the result back.
- **Tools:** `search_product_docs`, `estimate_service_cost`, `assess_flotation_readings`.
- **Grounding:** product facts cite brochure pages; cost figures are computed in code and
  list the reports they come from.
- **Data preparation:** brochures read from the PDFs, so each spec-table row stays on one
  line; service reports turned once into checked records, with gaps flagged rather than
  guessed.
- **Tracing:** optional Langfuse traces of every model and tool call.

## Steps

### 0. Setup

- [x] Set up the project skeleton

### 1. Product questions

- [x] Read the brochures page by page
- [x] Search the brochures by keyword
- [x] Answer product questions with a LangGraph agent
- [x] Trace agent turns in Langfuse

### 2. Service costs

- [x] Turn service reports into checked records
- [x] Estimate service visits from past reports

### 3. Flotation data (optional part)

- [x] Compare flotation readings with plant history

### 4. Documentation

- [x] Document the design, data findings and limits
- [ ] Add sample runs of the three brief prompts

## Decisions

| Date | Decision | Reason |
| --- | --- | --- |
| 13 Oct | The model picks a tool for each message; one routing rule sends the turn to the tool step or ends it | The brief asks the assistant to decide for itself; the rule stays small and visible |
| 13 Oct | An explicit LangGraph graph rather than a prebuilt agent | The routing is our own code, and the graph can be drawn |
| 13 Oct | An OpenAI model through LangChain, named in `.env` | Reliable tool calling and structured output; one line changes the model |
| 13 Oct | Brochures re-read from the PDFs | The provided text flattens spec tables into lists |
| 13 Oct | Keyword search (BM25) over brochure pages | Product codes such as PF-DS match exactly; no extra model needed |
| 13 Oct | Service costs computed in code from checked records | No invented or mis-added figures; every number traces to a report |
| 16 Oct | pypdfium2 reads the brochure PDFs | Kept 14 of 15 spec-table rows intact (pypdf and PyMuPDF kept 15, with font warnings or an AGPL licence) and was the fastest of six readers, with a small install and a permissive licence ([Measurements](#measurements)) |
| 16 Oct | Text clean-up only for what pypdfium2 outputs | Windows line breaks, icon glyphs that come out as control characters, and PDFium's mark for a hyphen at a line break; Unicode NFKC would turn "ColumnCell™" into "ColumnCellTM" |
| 17 Oct | Our own BM25 (about 30 lines) rather than a library | Same results as rank_bm25 on 24 test questions, no extra dependency, and every step of the scoring is visible ([Measurements](#measurements)) |
| 17 Oct | No stemming; hyphenated codes split into words | Stemming found one more answer but pushed demo prompt 1's answer page from 1st to 5th; splitting lets "PF DS" find "PF-DS" at no measured cost |
| 17 Oct | The model writes one card per brochure at ingest (product, kind, one sentence), copying the product name from the brochure's title | The agent learns which products exist without a hand-written list, and the two Larox PF editions print the same title, so they group as one product. Asking the model to reuse earlier names left them apart; asking "same product as one already described?" merged the PF-DS into them |
| 17 Oct | The model picks the search's brochure filter from the cards | Spec tables share few words with a question: the 14-chamber question finds its page 2nd within `larox-pf-ds`, 7th over all brochures |
| 17 Oct | At most 12 graph steps per question | Room for five rounds of tools and an answer; an even number, so a stopped turn still ends on tool results and the chat can go on |
| 17 Oct | Tracing through Langfuse's LangChain callback, on only when its three settings are in `.env` | Records the graph, each step, every model call (prompt, tokens, cost) and every tool call without changing the graph; a chat's thread becomes its Langfuse session |
| 17 Oct | `check` tests the Langfuse connection; `ask` and `chat` do not | With keys set but no server, a question still works but exits about 6 s later with one warning (measured); `check` finds that on demand without slowing every question |
| 17 Oct | Each service report is read once by the model into a fixed form, then checked in code | Four layouts and shorthand notes ("11-12h", "as per agreement + travel") defeat parsers, so one path reads them all. The model copies; code works out the cost status, the ex-VAT total and the rates, and flags gaps without filling them |
| 17 Oct | Equipment and job types are fixed lists the model picks from | Costs are grouped by equipment and job, which needs exact names; free names drift, as the product cards showed |
| 17 Oct | Nine reports checked by hand test the extraction, with the hand-counted cost statuses and flags | A repeatable measure of the reader on real data; it runs locally and skips where the data is absent |
| 17 Oct | One `ingest --rewrite` for everything the model writes | One flag to remember; redoing cards and records together is about 62 small calls |
| 18 Oct | A cost that names no currency, such as "$2,540", is read as US dollars by a rule in code, and flagged | The model rightly left "$" blank, since it could be any dollar. The three such reports come from Russia, Peru and Zambia, and the Peru and Zambia reports that name a currency use USD; one visible, tested rule replaces a guess |
| 18 Oct | Hours are taken only as stated: "about 8.4" is 8.4 and "11-12h" is 11.5; unclear hours and one-way travel stay blank | The first run's yes/no for approximate hours was inconsistent ("about 14.1" marked, "about 8.4" not), and one note's one-way travel time was read as the whole trip |
| 18 Oct | The form's examples are made up, never copied from the reports | Two examples had been copied from hand-checked reports (FSR-0016, FSR-0035), so their test could pass by copying; with made-up phrases, a pass shows the rule itself works |
| 18 Oct | A budget is built from pieces: hours on site from past jobs of the same kind on the same equipment, labour and travel from the same country, part prices from past invoices | No past visit matches a new one: demo prompt 2 has no PF-DS cloth job in Chile, and only 3 of the 6 PF-DS cloth jobs state a total, in three currencies. Hours depend on the job and rates on the country, so pieces can be combined |
| 18 Oct | Typical figure = the middle value of each piece; likely range = the middle 80% of every combination of past values | The median is not pulled by one long job (14.2 h). For demo prompt 2 the range is USD 1,759 to 3,072 from 648 combinations; the extremes (1,330 to 3,820) would assume every piece cheapest, or dearest, at once |
| 18 Oct | Weekend and emergency visits are left out, and "weekend" means only what a report says | They carry surcharges (FSR-0019: CAD 185/h against 120 to 140). The first reading had marked 10 more visits as weekend from their dates, though none said so or charged it |
| 18 Oct | A piece the reports lack is named, never filled: no total without labour and travel | The brief asks to say clearly what is not in the data; Russia and South Africa have no itemized rates |
| 18 Oct | Prices converted with a fixed table of 2024 averages, named in every answer; the answer uses the currency of the country's own reports | Reproducible and testable without a rates service; Chile's reports are in USD |
| 18 Oct | The model chooses the inputs; code does every sum, and the tool's text carries each total ready-made | The model reads numbers and never adds them up |
| 18 Oct | A cost line without a single number is dropped | One re-read turned "Cost: total as per agreement + travel" (FSR-0030) into two empty lines, which made it look like a cut-off table with an assumed currency; the hand-counted tests caught it |
| 18 Oct | Flotation readings are assessed by a statistics tool in code, not by the model or a trained model | The brief asks for an answer computed from the data. No single measurement links with silica beyond 0.22, so a predictive model would be weak and hard to explain; code-computed ranks are exact and testable |
| 18 Oct | Readings are ranked by the share of hours at least as bad, against the median and middle half | Demo prompt 3: 24% of hours had silica of 3.1% or more, 28% had iron of 64.5% or less, 20% both. It happens, but it is this plant's worst quarter, not "normal" |
| 18 Oct | The 6 measurements most linked with silica are reported, computed, with their middle value in the best and worst quarter of hours | No hand-picked list, so another plant's file works too; here it brought up column levels (about 448 against 395), which a list of the usual levers would have missed |
| 18 Oct | Measurements are reported as associations with their limits, never as causes | Every link is weak, and amine is higher in poor hours, most likely because operators add more when silica rises |
| 18 Oct | Python's standard library, not pandas | 4,097 rows; medians, quartiles and correlation are built in, so no 40 MB dependency |
| 18 Oct | What Metso could offer comes from the brochure search, cited | Plant numbers come from the plant data and product facts from the brochures, each with its source |
| 18 Oct | The flotation text states the verdict's number ("worse than 76% of the plant's hours"), and the prompt asks to lead with whether readings are typical for that plant | The first live answer called 3.1% silica "not unusual" and turned "24% of hours were this bad" round awkwardly; code now does that flip |
| 18 Oct | The prompt's product list marks brochure names as code: `columncell` (2024) | The model once passed "columncell (2024)" whole as a brochure name; the search refused it, and the retry cost a model call |
| 18 Oct | Flotation suggestions come from products that act on the measurements the tool reports | Runs of demo prompt 3 suggested CellStation (level and air control, where the data points) or ColumnCell (fine particles, which the data never mentions) |
| 18 Oct | No fixed set of test questions run against the model: the brief's three prompts ran on both models, and the edge cases were checked by hand | The brief asks for a small, working agent; a test set pays off when prompts keep changing. Unit tests still cover all the code, in CI |

## Limits and scale-up

Out of scope for this assignment, noted as they come up, with what would change.

- **Conversation length:** earlier tool results stay in the chat, so each turn costs more
  (3,300 to 9,300 tokens over three questions). Trim or summarise old tool results.
- **Many products:** the prompt lists every product, about 50 tokens each. Past a few
  hundred, a "find products" tool replaces the list.
- **Many pages:** keyword search in memory suits thousands of pages. Beyond that, a search
  service with keyword and embedding search, a reranker and metadata filters, behind the
  same tool.
- **Long documents:** search by section instead of by page, give the agent a map of each
  document, and add a tool to read neighbouring pages.
- **Changed brochures or reports:** cards and records are cached by file name, so a new
  edition under an old name needs `ingest --rewrite`. At scale, key the cache by file hash.
- **Many reports:** read them as a batch job (OpenAI's Batch API costs half), keep the
  records in a database, check a random sample each month to measure accuracy per field,
  and send flagged records to a review queue.
- **Fine-tuning:** not worth it for 50 reports. At high volume, the corrections made in the
  review queue could train a smaller, cheaper model to read reports.
- **Testing the agent:** the brief's three prompts ran on two models, and a question
  missing details and a follow-up were checked by hand. A larger system would keep a fixed
  set of questions with the tools and facts each answer needs, run on every prompt change,
  for example as Langfuse experiments.
- **One model for everything:** one setting names the model for ingest and for answers.
  Ingest reads each document once, so a stronger model there costs little and every answer
  gains from its reading; answers run on every question, where a smaller model keeps the
  call fast and cheap. A second setting would split them.
- **Combinations:** the likely range tries every combination of past values (648 for demo
  prompt 2). With thousands of past visits, a random sample of combinations gives the same
  range.
- **Exchange rates:** a fixed table of 2024 averages. A live system would take them from
  the finance system on the visit's date.
- **Thin data:** a piece from one report (Peru's rates) is warned about. More visits per
  country, or rates from a price list, would make such estimates firmer.
- **Job types are generous:** a record lists every kind of work its visit touched, so "same
  kind of job" means "included that work". Job codes from a field-service system would be
  sharper.
- **Two notes name only a city** (FSR-0036 Arequipa, FSR-0038 Rustenburg), so their country
  is blank and their travel times unused. A site list would fill it in.
- **Saved records:** each record keeps the model's reading together with what code worked
  out from it, so a change to the checks means reading the reports again. Saving only the
  reading, and working the rest out on load, would avoid those calls.
- **One plant's history:** the readings are judged against one iron ore plant in 2017, not
  against the customer's own plant. With the customer's data, the same tool would compare
  them with their own history; with many plants, with plants of the same ore and process.
- **Associations only:** the tool shows which measurements differed between good and poor
  hours. Finding what changes silica would need controlled trials or a process model.
- **New equipment or job types:** each fixed list needs one more line; until then, new
  equipment is filed as `other`.
- **Memory:** chats live in memory and end with the session; production would keep them in
  a database.
- **Speed:** searching through the agent costs one extra model call per question. If that
  matters, pre-load the top pages for product questions.
- **Users:** built for Metso's salespeople, so it shows internal data such as past costs. A
  public version would need sign-in, guardrails against prompt injection, and no internal
  cost data.
- **Tracing:** one local Langfuse in Docker. A team would share one instance, attach
  evaluation scores to traces and keep prompt versions in Langfuse's prompt registry.
  Traces hold whole conversations, so they stay self-hosted or masked.

## Measurements

### PDF readers (16 Oct)

The provided text flattens every spec table, so six readers were compared on all 12
brochures (73 pages): how many of 15 known spec-table rows keep their values on one line,
search quality (BM25 over the pages, 10 questions with known answer pages), and speed.
Measured once with a local script, which is not part of the repository.

| Reader | Rows kept | hit@5 | MRR | Time | Install | Licence |
| --- | --- | --- | --- | --- | --- | --- |
| Provided `.md` | 0 of 15 | 9/10 | 0.91 | none | none | none |
| **pypdfium2** | 14 of 15 | 9/10 | 0.91 | 0.4 s | 8 MB | Apache-2.0 or BSD-3 |
| pypdf | 15 of 15 | 9/10 | 0.92 | 1.5 s | 2 MB | BSD-3 |
| pdfminer.six | 0 of 15 | 9/10 | 0.92 | 3.1 s | 21 MB | MIT |
| pdfplumber (layout) | 14 of 15 | 9/10 | 0.92 | 4.2 s | 43 MB | MIT |
| PyMuPDF | 15 of 15 | 9/10 | 0.91 | 0.5 s | 49 MB | AGPL-3.0 |

- pypdfium2's one miss is spacing, not a broken row: it reads `pcs68` for "pcs 6 8",
  where the PDF sets those characters very close together.
- pypdf keeps all 15 rows but warns about fonts it cannot fully decode; PyMuPDF keeps all
  15 but is AGPL-licensed.
- Search hardly depends on the reader: each finds an answer page in the top 5 for 9 of
  10 questions. The miss, "weight of a tower press with 14 chambers", is what the search
  tool's brochure filter is for.
- Times come from one laptop run and vary between runs; install sizes were measured
  separately with `uv pip install --target`.

### Search design (17 Oct)

BM25 over the 73 pages, measured on 24 questions worded the way the agent might search,
each with its known answer pages, plus 3 questions in a salesperson's own words.

| Variant | Answer in top 5 | MRR | Demo prompt 1, raw words |
| --- | --- | --- | --- |
| rank_bm25 library | 22 of 24 | 0.91 | 1st |
| **Own BM25, hyphens split (chosen)** | 22 of 24 | 0.91 | 1st |
| Own BM25, hyphenated codes kept whole | 22 of 24 | 0.91 | 1st |
| Own BM25 with stemming | 23 of 24 | 0.87 | 5th |
| Own BM25 with the brochure name on every page | 22 of 24 | 0.90 | 1st |

- All 3 questions in a salesperson's own words rank their answer page first.
- The two misses: "weight of a tower press with 14 chambers" asks for a spec table that
  shares few words with the question (7th; 2nd when the search is kept within
  `larox-pf-ds`), and "number of filter plates in a PF 60", where every Larox PF spec page
  shares those words (the answer pages come 6th and 7th).
- A test on the real brochures fails if fewer than 22 of the 24 find their answer page in
  the top 5, or if demo prompt 1's answer page stops coming first.
