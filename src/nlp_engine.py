"""
NLP Query Engine using LangChain for natural language to SQL conversion
"""
import os
from typing import Dict, Any
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain.agents import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain.agents.agent_types import AgentType
from langchain.agents.agent_toolkits import SQLDatabaseToolkit

load_dotenv()

class TexasFinanceNLPEngine:
    """Natural language query engine for Texas school finance data"""
    
    def __init__(self):
        # Initialize database connection
        db_url = os.getenv("SUPABASE_DB_URL")
        if not db_url:
            raise ValueError("SUPABASE_DB_URL not found in environment variables")
        
        # Connect to specific views only (for safety)
        self.db = SQLDatabase.from_uri(
            db_url, 
            include_tables=["v_finance_summary", "v_anomaly_flags"]
        )
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4o-mini", 
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Create SQL toolkit
        toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        
        # System prompt with schema context
        self.system_prefix = """You are a helpful assistant that converts natural language questions about Texas school district finances into SQL queries.

Available views:
1. v_finance_summary - Main financial data with columns:
   - district_number (6-digit code)
   - district_name (e.g., 'DALLAS ISD')
   - year (2008-2024)
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

Rules:
- Use ILIKE for fuzzy district name matching
- Always include ORDER BY for time series data
- Limit results to prevent overload (default LIMIT 100)
- Round financial figures to 2 decimal places for readability
- When asked about "spending", use total_spend unless specified otherwise
- For year ranges, use BETWEEN operator

Be concise and clear in your responses. If asked for trends, calculate year-over-year changes."""

        # Create agent
        self.agent = create_sql_agent(
            llm=self.llm,
            toolkit=toolkit,
            agent_type=AgentType.OPENAI_FUNCTIONS,
            verbose=True,  # Set to False in production
            prefix=self.system_prefix,
            max_iterations=5,
            early_stopping_method="generate"
        )
    
    def query(self, question: str) -> Dict[str, Any]:
        """
        Execute a natural language query and return results
        
        Args:
            question: Natural language question about Texas school finances
            
        Returns:
            Dict with 'answer' and optionally 'data' keys
        """
        try:
            # Add safety constraints to the question
            safe_question = f"{question}\nPlease limit results to 100 rows maximum."
            
            # Execute query
            result = self.agent.invoke({"input": safe_question})
            
            # Extract the output
            output = result.get("output", "No result returned")
            
            return {
                "success": True,
                "answer": output,
                "question": question
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "question": question
            }
    
    def get_sample_queries(self) -> list:
        """Return sample queries for testing/documentation"""
        return [
            "Which district has the highest spending per student in 2024?",
            "Show me Dallas ISD spending trends from 2015 to 2020",
            "Find all districts with revenue drops greater than 15% in the last year",
            "What's the average per-student spending across all districts in 2023?",
            "List districts with enrollment decline but increased spending",
            "Compare Houston ISD and Austin ISD spending per student over time",
            "Which districts have the most debt service relative to total spending?",
            "Show anomaly flags for districts in 2024",
            "What's the total state education budget across all districts by year?",
            "Find districts spending less than $10,000 per student"
        ]

# Example usage
if __name__ == "__main__":
    # Initialize engine
    engine = TexasFinanceNLPEngine()
    
    # Test queries
    test_queries = [
        "Show me Dallas ISD spending per student from 2018 to 2023",
        "Which districts have anomaly flags in 2024?",
        "What's the average enrollment across all districts?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        result = engine.query(query)
        if result["success"]:
            print(f"Answer: {result['answer']}")
        else:
            print(f"Error: {result['error']}")
