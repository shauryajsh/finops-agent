# BigQuery FinOps Agent

BigQuery charges you for bytes scanned, not rows returned. A stray `SELECT *` or a missing partition filter can quietly cost 10-80x more than it should, and most teams don't notice until the bill shows up. This agent reads BigQuery's own job history, flags the queries actually worth caring about, explains why using an LLM that's given the real table schema (not just the query text), proposes a fix, and checks the fix actually reduces bytes scanned before suggesting it. Findings get posted to Slack and opened as GitHub issues automatically, once a week.

## How it works

BigQuery already logs every query's cost metadata - no ingestion step needed. A dbt project cleans that up and flags queries in the top cost percentile (scaled to whatever a deployment's real spend looks like, not a fixed dollar number) plus queries that recur often enough that their total cost adds up even if no single run looks expensive.

Flagged queries go through a free rule-based pre-filter first (catches SELECT *, wildcard scans, COUNT(DISTINCT), unbounded ORDER BY instantly). Anything left goes to an LLM (Gemini, falling back to Groq if it's down or rate-limited) which reasons over the actual schema and partitioning info and writes a diagnosis plus a corrected query. The fix gets dry-run checked against BigQuery for a real byte-reduction number before it's ever shown to anyone.

Public BigQuery datasets
│
▼
BigQuery INFORMATION_SCHEMA (auto-logged, nothing to build)
│
▼
dbt: staging → percentile-flagged + recurring-pattern marts
│
▼
rule-based pre-filter ──► LLM diagnosis + dry-run-validated fix
│
▼
Slack digest + GitHub issues

Tables get discovered live from BigQuery rather than hardcoded. Runs on a weekly GitHub Actions schedule. Auth to GCP is via Workload Identity Federation, so there's no service account key sitting in a secret anywhere.

## On-demand API

Alongside the weekly job, the same diagnosis logic is also available as a REST API. A FastAPI wrapper exposes /diagnose so a query can be checked before it ever runs, in a CI pipeline reviewing a pull request, for example, rather than only after it's already shown up in real billing history.

It runs on Cloud Run, deployed straight from source with no Dockerfile needed. It reuses the same service account and IAM roles already set up in Terraform, so there's no separate infrastructure to manage. The API keeps its own smaller requirements.txt inside agent/src, since it never touches dbt, and pulling in dbt's own dependencies caused a real version conflict at build time that a shared requirements file was silently hiding.

The service stays private by default, only callable with a valid GCP identity token, not open to the public internet.

## Eval results

Ran 60 cases across 7 real anti-pattern categories (SELECT *, missing partition pruning, wildcard scans, COUNT DISTINCT, JS UDFs, fan-out joins, plus known-fine queries that shouldn't get flagged at all), built against real public BigQuery tables.

Rule-based: 43/60. LLM: 49/60.

Worth being honest about that number: a chunk of the LLM's "misses" are the eval being picky about exact wording, not the model actually being wrong - it explained a wildcard scan correctly without using the word "wildcard," for instance, and got marked wrong. Two real gaps remain: the prompt doesn't currently tell it that COUNT(DISTINCT) is expensive on its own, and it doesn't know joins can fan out rows.

## Known limitations

- The rule-based filter only catches literal text patterns. Write the same waste a different way and it's invisible.
- Recurring-query detection groups by exact query text (whitespace-normalized). A real scheduled query with a changing date filter wouldn't get grouped as the same recurring pattern.
- When the fix trims a SELECT *, it's guessing which columns are actually needed downstream - a reasonable guess, not a guarantee.
- Free tiers cap out fast (Gemini: 20 requests/day, Groq: 8,000 tokens/minute). Real production volume needs a paid tier.
- Table discovery is dynamic for a deployment's own project, but the demo also names a fixed list of external public-data datasets to search, since bigquery-public-data itself is too large to enumerate in full.
- The API is deliberately private, callable only with a valid GCP identity token. It's meant for the account's own CI or internal use, not as a shared public service.

## Setup

```bash
git clone https://github.com/shauryajsh/finops-agent.git
cd finops-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your own project, keys, webhook
```

You'll need a GCP project with BigQuery on, and dbt_finops/ pointed at your own dataset. For the weekly automated run, fork the repo and add the secrets/variables listed in .github/workflows/weekly_report.yml.

## Stack

BigQuery, dbt, Python, Gemini + Groq, Terraform, GitHub Actions, Cloud Run, FastAPI.

## Related work

AWS has its own FinOps Agent for AWS spend - nothing official exists for BigQuery. There's a Google professional-services example and an independent project called FinSavant that both do conversational billing Q&A. This one's different in shape: it doesn't wait to be asked, it watches and tells you.

## License

MIT