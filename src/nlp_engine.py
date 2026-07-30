"""
NLP Query Engine: natural language to SQL over the public finance views.

Uses LangChain 1.x `create_agent` (the supported agent API) with the SQL
toolkit. Note: `langchain-community` (home of SQLDatabase/SQLDatabaseToolkit)
was sunset in June 2026; it still works but is no longer actively maintained.
Track https://github.com/langchain-ai/langchain-community/issues/674 for the
migration path to standalone integration packages.
"""
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI

from .sample_queries import SAMPLE_QUERIES

load_dotenv()

SYSTEM_PROMPT = """You are a helpful assistant that converts natural language questions
about Texas school district finances into SQL queries.

Available views:
1. v_finance_summary - Main financial data with columns:
   - district_number (6-digit code)
   - district_name (e.g., 'DALLAS ISD')
   - year (2009-2025)
   - total_revenue (all funds total operating revenue)
   - total_spend (all funds total disbursements)
   - enrollment (fall survey enrollment count)
   - spend_per_student (calculated: total_spend / enrollment)
   - revenue_per_student (calculated: total_revenue / enrollment)
   - instruction_spend (instructional expenditures)
   - debt_service (debt service payments)
   - capital_projects (capital project spending)

2. v_anomaly_flags - Detected financial anomalies with columns:
   - All columns from v_finance_summary plus:
   - revenue_drop_flag (true if revenue dropped >15% YoY)
   - spend_spike_flag (true if spending increased >20% with flat enrollment)
   - per_student_spike_flag (true if per-student spending increased >15%)
   - enrollment_decline_flag (true if enrollment declined >10%)

Ground truth you can rely on (use these to sanity-check any answer):
- The data covers 1,310 distinct districts, 20,587 district-year records,
  fiscal years 2009 through 2025.

Rules:
- Only run SELECT statements; never modify data
- Use ILIKE for fuzzy district name matching
- Always include ORDER BY for time series data
- COUNTING IS NOT LIMITING. Never put LIMIT on an aggregate query
  (COUNT, SUM, AVG, MIN, MAX). To answer "how many", use COUNT(*) or
  COUNT(DISTINCT col) and report that number. NEVER count the rows a query
  returned and present that as a total — a LIMIT would make it wrong.
- LIMIT belongs only on queries that LIST rows, and 100 is a reasonable
  default there.
- If a listing query returns exactly as many rows as its LIMIT, say the
  result may be truncated rather than implying it is complete.
- If your answer contradicts the ground truth above, your query is wrong.
  Re-check it rather than reporting the contradiction.
- Round financial figures to 2 decimal places for readability
- When asked about "spending", use total_spend unless specified otherwise
- For year ranges, use BETWEEN operator

Be concise and clear in your responses. If asked for trends, calculate year-over-year changes."""


class TexasFinanceNLPEngine:
    """Natural language query engine for Texas school finance data"""

    def __init__(
        self,
        db_url: Optional[str] = None,
        llm: Optional[Any] = None,
        db: Optional[SQLDatabase] = None,
    ):
        if db is None:
            # NLP_DB_URL is the least-privilege role from sql/create_nlp_role.sql:
            # SELECT on the two public views, read-only transactions, nothing
            # else. Prefer it. SUPABASE_DB_URL is the owner connection and is
            # only a fallback so the feature still works before the role is
            # provisioned — `include_tables` below limits what the agent is told
            # about, not what the database will let it run.
            db_url = db_url or os.getenv("NLP_DB_URL") or os.getenv("SUPABASE_DB_URL")
            if not db_url:
                raise ValueError(
                    "Neither NLP_DB_URL nor SUPABASE_DB_URL found in environment"
                )
            # Connect to the two public read-only views only (least privilege)
            db = SQLDatabase.from_uri(
                db_url,
                include_tables=["v_finance_summary", "v_anomaly_flags"],
                view_support=True,
            )
        if llm is None and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        self.db = db

        self.llm = llm or ChatOpenAI(
            model=os.getenv("NLP_MODEL", "gpt-4o-mini"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        self.agent = create_agent(
            self.llm,
            toolkit.get_tools(),
            system_prompt=SYSTEM_PROMPT,
        )

    def query(self, question: str) -> Dict[str, Any]:
        """
        Execute a natural language query and return results

        Args:
            question: Natural language question about Texas school finances

        Returns:
            Dict with 'success', 'question' and 'answer' or 'error' keys
        """
        try:
            safe_question = f"{question}\nPlease limit results to 100 rows maximum."
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": safe_question}]},
                config={"recursion_limit": 15},
            )
            messages = result.get("messages", [])
            output = messages[-1].content if messages else "No result returned"

            return {
                "success": True,
                "answer": output,
                "question": question,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "question": question,
            }

    def get_sample_queries(self) -> list:
        """Return sample queries for testing/documentation"""
        return SAMPLE_QUERIES


# Example usage: python -m src.nlp_engine
if __name__ == "__main__":
    engine = TexasFinanceNLPEngine()

    test_queries = [
        "Show me Dallas ISD spending per student from 2018 to 2023",
        "Which districts have anomaly flags in 2024?",
        "What's the average enrollment across all districts?",
    ]

    for q in test_queries:
        print(f"\nQuery: {q}")
        print("-" * 50)
        result = engine.query(q)
        if result["success"]:
            print(f"Answer: {result['answer']}")
        else:
            print(f"Error: {result['error']}")
