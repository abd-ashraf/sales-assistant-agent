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
- [ ] Search the brochures by keyword
- [ ] Answer product questions with a LangGraph agent
- [ ] Trace agent turns in Langfuse

### 2. Service costs

- [ ] Turn service reports into checked records
- [ ] Estimate service visits from past reports

### 3. Flotation data (optional part)

- [ ] Compare flotation readings with plant history

### 4. Evaluation

- [ ] Check routing and grounding on fixed scenarios
- [ ] Fix what the scenario run showed

### 5. Documentation

- [ ] Document the design, data findings and limits
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
