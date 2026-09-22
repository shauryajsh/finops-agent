"""FastAPI wrapper exposing the FinOps agent's diagnosis logic on demand.

Reuses the exact functions the scheduled weekly job already calls - this
just makes them callable directly, not only on a schedule.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from llm_agent import get_flagged_queries, get_recurring_queries, diagnose_and_fix, validate_fix

app = FastAPI(title="FinOps Agent API")


class DiagnoseRequest(BaseModel):
    query: str


@app.get("/health")
def health():
    """Basic health check."""
    return {"status": "ok"}


@app.get("/flagged-queries")
def flagged_queries():
    """Returns currently flagged expensive queries."""
    rows = get_flagged_queries()
    return [
        {
            "query_owner": row.query_owner,
            "query": row.query,
            "estimated_cost_usd": row.estimated_cost_usd,
            "avg_cost_usd": row.avg_cost_usd,
        }
        for row in rows
    ]


@app.get("/recurring-queries")
def recurring_queries():
    """Returns currently flagged recurring query patterns."""
    rows = get_recurring_queries()
    return [
        {
            "most_recent_owner": row.most_recent_owner,
            "run_count": row.run_count,
            "total_cost_usd": row.total_cost_usd,
        }
        for row in rows
    ]


@app.post("/diagnose")
def diagnose(request: DiagnoseRequest):
    """Diagnoses any query on demand and returns a validated fix if one exists."""
    result = diagnose_and_fix(request.query)
    validation = validate_fix(request.query, result["fixed_query"])

    response = {
        "has_issue": result.get("has_issue"),
        "explanation": result["explanation"],
        "fixed_query": result["fixed_query"],
    }

    if result["fixed_query"] is None:
        response["cost_impact"] = None
    elif validation["valid"]:
        original_gb = validation["original_bytes"] / 1024**3
        fixed_gb = validation["fixed_bytes"] / 1024**3
        reduction_pct = (1 - validation["fixed_bytes"] / validation["original_bytes"]) * 100
        response["cost_impact"] = {
            "original_gb": round(original_gb, 3),
            "fixed_gb": round(fixed_gb, 3),
            "reduction_percent": round(reduction_pct, 1),
        }
    else:
        response["cost_impact"] = {"error": validation.get("error", "could not validate fix")}

    return response