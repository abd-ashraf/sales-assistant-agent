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
- **Data preparation:** brochures re-read from the PDFs with their layout kept; service
  reports turned once into checked records, with gaps flagged rather than guessed.
- **Tracing:** optional Langfuse traces of every model and tool call.

## Steps

### 0. Setup

- [x] Set up the project skeleton

### 1. Product questions

- [ ] Read the brochures page by page
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
