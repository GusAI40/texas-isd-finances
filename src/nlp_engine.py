"""Natural-language queries over the two public finance views.

LangChain's current SQL-agent guide builds application-owned tools with
``langchain.tools.tool``. That is the supported replacement for the archived
``langchain-community`` SQL toolkit: this module owns its SQLAlchemy adapter,
relation allowlist, read-only validator, schema tool, query tool, and checker.

The model provider is resolved in :mod:`src.llm_config`. DeepSeek and OpenAI
are both reachable through ``ChatOpenAI`` because DeepSeek implements the
OpenAI request format, including the tool-calling protocol this agent needs;
only the base URL and model name change.
"""
import os
import re
from typing import Any, Dict, Iterable, Optional, Sequence

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlglot import ErrorLevel, exp, parse
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.scope import build_scope

from .llm_config import resolve_llm_config
from .sample_queries import SAMPLE_QUERIES

load_dotenv()

NLP_RELATIONS = ("v_finance_summary", "v_anomaly_flags")
TOOL_ROW_LIMIT = 100


class SQLPolicyError(ValueError):
    """A controlled validation message that is safe to return to the agent."""


# A prompt is not a security boundary. The production nlp_reader role remains
# the decisive authorization control; the lexical denylist gives early,
# readable errors before the exact AST allowlist below makes the execution
# decision.
_WRITE_KEYWORDS = re.compile(
    r"\b(?:alter|analyze|call|cluster|comment|copy|create|deallocate|delete|"
    r"discard|do|drop|execute|grant|insert|listen|load|lock|merge|notify|"
    r"prepare|refresh|reindex|reset|revoke|security|set|truncate|unlisten|"
    r"update|vacuum|into)\b",
    re.IGNORECASE,
)

# SQL SELECTs can still mutate server-session state through functions such as
# pg_advisory_lock(), set_config(), pg_notify(), and pg_sleep(). PostgreSQL's
# read-only transaction flag does not make those harmless, especially behind
# a transaction pooler where session state may reach another request. Parse
# every statement and allow only the exact syntax and pure functions finance
# questions need. Unlisted syntax fails closed, so TableSample, custom
# operators, anonymous/qualified functions, UDTFs, locking, INTO, and future
# SQLGlot nodes cannot become new execution surfaces silently. An upgrade of
# SQLGlot is therefore a reviewed security change.
_ALLOWED_SELECT_NODE_TYPES = frozenset(
    {
        # Query shape.
        exp.Select,
        exp.Union,
        exp.Intersect,
        exp.Except,
        exp.Subquery,
        exp.With,
        exp.CTE,
        exp.From,
        exp.Join,
        exp.Where,
        exp.Group,
        exp.Having,
        exp.Order,
        exp.Ordered,
        exp.Limit,
        exp.Offset,
        exp.Distinct,
        exp.Window,
        exp.WindowSpec,
        exp.Filter,
        exp.WithinGroup,
        # Sources and scalar values.
        exp.Table,
        exp.TableAlias,
        exp.Column,
        exp.Identifier,
        exp.Star,
        exp.Alias,
        exp.Literal,
        exp.Boolean,
        exp.Null,
        exp.Tuple,
        exp.DataType,
        exp.DataTypeParam,
        exp.Var,
        exp.Kwarg,
        exp.Paren,
        # Arithmetic, predicates, and conditionals.
        exp.Add,
        exp.Sub,
        exp.Mul,
        exp.Div,
        exp.Mod,
        exp.Neg,
        exp.And,
        exp.Or,
        exp.Not,
        exp.EQ,
        exp.NEQ,
        exp.GT,
        exp.GTE,
        exp.LT,
        exp.LTE,
        exp.Is,
        exp.Between,
        exp.In,
        exp.Exists,
        exp.Like,
        exp.ILike,
        exp.Case,
        exp.If,
        # Reviewed pure PostgreSQL built-ins. These are concrete parser nodes;
        # exp.Anonymous is intentionally absent.
        exp.Abs,
        exp.ArrayAgg,
        exp.Avg,
        exp.Cast,
        exp.Ceil,
        exp.Coalesce,
        exp.Concat,
        exp.Count,
        exp.CumeDist,
        exp.CurrentDate,
        exp.CurrentTimestamp,
        exp.DenseRank,
        exp.Exp,
        exp.Extract,
        exp.FirstValue,
        exp.Floor,
        exp.Greatest,
        exp.GroupConcat,
        exp.Lag,
        exp.LastValue,
        exp.Lead,
        exp.Least,
        exp.Length,
        exp.Ln,
        exp.Log,
        exp.LogicalAnd,
        exp.LogicalOr,
        exp.Lower,
        exp.MakeInterval,
        exp.Max,
        exp.Min,
        exp.Ntile,
        exp.Nullif,
        exp.PercentileCont,
        exp.PercentRank,
        exp.Pow,
        exp.Rank,
        exp.Replace,
        exp.Round,
        exp.RowNumber,
        exp.Sign,
        exp.Sqrt,
        exp.Stddev,
        exp.StddevPop,
        exp.StddevSamp,
        exp.Substring,
        exp.Sum,
        exp.TimeToStr,
        exp.TimestampTrunc,
        exp.Trim,
        exp.Upper,
        exp.Variance,
        exp.VariancePop,
    }
)


def _sql_code_only(sql: str) -> str:
    """Mask strings, quoted identifiers, and comments before validation.

    The returned text preserves newlines and punctuation in executable SQL,
    while replacing non-code regions with spaces. PostgreSQL dollar-quoted
    strings and nested block comments are handled as well as ordinary SQL
    quotes/comments. This is deliberately a validator, not a SQL parser; the
    database read-only role is still the final authorization boundary.
    """

    chars = list(sql)
    masked = list(sql)
    i = 0
    length = len(chars)

    def blank(start: int, end: int) -> None:
        for pos in range(start, end):
            if masked[pos] not in "\r\n":
                masked[pos] = " "

    while i < length:
        if sql.startswith("--", i):
            end = sql.find("\n", i + 2)
            end = length if end == -1 else end
            blank(i, end)
            i = end
            continue

        if sql.startswith("/*", i):
            start = i
            i += 2
            depth = 1
            while i < length and depth:
                if sql.startswith("/*", i):
                    depth += 1
                    i += 2
                elif sql.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise SQLPolicyError("unterminated SQL block comment")
            blank(start, i)
            continue

        if chars[i] in ("'", '"'):
            quote = chars[i]
            start = i
            i += 1
            while i < length:
                if chars[i] == quote:
                    if i + 1 < length and chars[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else:
                raise SQLPolicyError("unterminated SQL quoted value")
            blank(start, i)
            continue

        if chars[i] == "$":
            tag_match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if tag_match:
                tag = tag_match.group(0)
                start = i
                i += len(tag)
                end = sql.find(tag, i)
                if end == -1:
                    raise SQLPolicyError("unterminated SQL dollar-quoted value")
                i = end + len(tag)
                blank(start, i)
                continue

        i += 1

    return "".join(masked)


def _assert_select_only(sql: str, *, qualify_relations: bool = False) -> str:
    """Return one parsed, policy-safe SELECT (non-recursive CTEs allowed).

    Keyword filtering catches obvious writes with useful errors. The SQLGlot
    AST is the security boundary: it identifies actual source relations,
    functions, locking/INTO nodes, and nested statements rather than treating
    underscores, comments, aliases, or CTEs as trustworthy syntax.
    """

    if not isinstance(sql, str) or not sql.strip():
        raise SQLPolicyError("query must be a non-empty SQL string")

    code = _sql_code_only(sql).strip()
    if not re.match(r"^(?:select|with)\b", code, re.IGNORECASE):
        raise SQLPolicyError("only SELECT statements are allowed")

    match = _WRITE_KEYWORDS.search(code)
    if match:
        raise SQLPolicyError(
            f"read-only query rejected keyword: {match.group(0).upper()}")

    try:
        statements = parse(sql, read="postgres", error_level=ErrorLevel.RAISE)
    except ParseError as exc:
        raise SQLPolicyError("query is not valid PostgreSQL SELECT syntax") from exc
    if len(statements) != 1 or statements[0] is None:
        raise SQLPolicyError("only one SQL statement is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SQLPolicyError("only SELECT statements are allowed")
    if any(with_.args.get("recursive") for with_ in tree.find_all(exp.With)):
        raise SQLPolicyError("recursive CTEs are not allowed")
    if any(
        data_type.this == exp.DataType.Type.USERDEFINED
        for data_type in tree.find_all(exp.DataType)
    ):
        raise SQLPolicyError("user-defined SQL types are not allowed")

    for node in tree.walk():
        if type(node) not in _ALLOWED_SELECT_NODE_TYPES:
            if isinstance(node, exp.Func):
                name = node.name or node.sql_name() or "anonymous"
                raise SQLPolicyError(f"SQL function {name.upper()} is not allowed")
            raise SQLPolicyError(
                f"SQL expression {type(node).__name__} is not allowed")

    try:
        root_scope = build_scope(tree)
        if root_scope is None:
            raise SQLPolicyError("query has no analyzable SELECT scope")
        sources = [
            source
            for scope in root_scope.traverse()
            for _alias, (_node, source) in scope.selected_sources.items()
            if isinstance(source, exp.Table)
        ]
    except OptimizeError as exc:
        raise SQLPolicyError("query sources could not be safely resolved") from exc

    allowed = set(NLP_RELATIONS)
    for source in sources:
        name = source.name.lower()
        database = source.db.lower()
        catalog = source.catalog.lower()
        if (
            not name
            or name not in allowed
            or catalog
            or database not in ("", "public")
        ):
            shown = ".".join(part for part in (catalog, database, name) if part)
            raise SQLPolicyError(
                f"relation {shown or '<table function>'} is not allowed")
        if qualify_relations:
            # Execution sets search_path to pg_catalog only so an unqualified
            # function cannot resolve to a side-effectful helper in public.
            # Qualify the two reviewed views after validation instead.
            source.set("catalog", None)
            source.set("db", exp.to_identifier("public"))
            source.set("this", exp.to_identifier(name))

    return tree.sql(dialect="postgres") if qualify_relations else sql


def _truncate(value: Any, max_length: int = 300) -> Any:
    if isinstance(value, str) and len(value) > max_length:
        return value[: max_length - 3] + "..."
    return value


class FinanceSQLDatabase:
    """Small SQLAlchemy adapter restricted to the finance agent's two views."""

    def __init__(
        self,
        engine: Engine,
        include_relations: Sequence[str] = NLP_RELATIONS,
    ) -> None:
        self._engine = engine
        self._inspector = inspect(engine)
        self._schema = "public" if engine.dialect.name == "postgresql" else None
        available = self._available_relations()
        requested = set(include_relations)
        missing = requested - available
        if missing:
            raise ValueError(f"include_relations {missing} not found in database")
        self._relations = tuple(sorted(requested))

    @classmethod
    def from_uri(
        cls,
        database_uri: str,
        include_relations: Sequence[str] = NLP_RELATIONS,
    ) -> "FinanceSQLDatabase":
        return cls(create_engine(database_uri), include_relations=include_relations)

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    def _available_relations(self) -> set[str]:
        names: set[str] = set()
        for method_name in (
            "get_table_names",
            "get_view_names",
            "get_materialized_view_names",
        ):
            method = getattr(self._inspector, method_name, None)
            if method is None:
                continue
            try:
                names.update(method(schema=self._schema) if self._schema else method())
            except NotImplementedError:
                continue
        return names

    def get_usable_table_names(self) -> list[str]:
        """Keep the legacy method name because the SQL tool vocabulary uses it."""

        return list(self._relations)

    def _quoted_relation(self, relation: str) -> str:
        if relation not in self._relations:
            raise SQLPolicyError(
                f"table_names {{{relation!r}}} not found in database")
        quote = self._engine.dialect.identifier_preparer.quote_identifier
        relation_name = quote(relation)
        return f"{quote(self._schema)}.{relation_name}" if self._schema else relation_name

    def _execute(self, query: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        query = _assert_select_only(
            query,
            qualify_relations=self.dialect == "postgresql",
        )
        with self._engine.connect() as connection:
            with connection.begin():
                # The nlp_reader role defaults every transaction to read-only.
                # Reassert it per transaction on Postgres as defense in depth
                # if a caller injects an accidentally privileged explicit URL.
                if self.dialect == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.exec_driver_sql("SET LOCAL search_path TO pg_catalog")
                    connection.exec_driver_sql("SET LOCAL statement_timeout = '20s'")
                result = connection.execute(text(query))
                columns = list(result.keys())
                rows = [
                    tuple(_truncate(value) for value in row)
                    for row in result.fetchmany(TOOL_ROW_LIMIT + 1)
                ]
        return columns, rows

    def run(self, query: str) -> str:
        """Execute a validated read and match the former toolkit's result shape."""

        _columns, rows = self._execute(query)
        truncated = len(rows) > TOOL_ROW_LIMIT
        visible_rows = rows[:TOOL_ROW_LIMIT]
        output = str(visible_rows) if visible_rows else ""
        if truncated:
            output += (
                "\nResult truncated after 100 rows. Use COUNT() for a total or "
                "narrow the listing query."
            )
        return output

    def get_table_info(self, table_names: Optional[Iterable[str]] = None) -> str:
        """Return column metadata and three sample rows for allowed relations."""

        names = list(table_names) if table_names is not None else list(self._relations)
        missing = set(names) - set(self._relations)
        if missing:
            raise SQLPolicyError(f"table_names {missing} not found in database")

        sections = []
        for relation in names:
            quoted = self._quoted_relation(relation)
            columns = self._inspector.get_columns(relation, schema=self._schema)
            definitions = ",\n".join(
                f"    {self._engine.dialect.identifier_preparer.quote_identifier(column['name'])} "
                f"{column['type']}"
                for column in columns
            )
            schema = f"RELATION {quoted} (\n{definitions}\n)"
            sample_columns, rows = self._execute(f"SELECT * FROM {quoted} LIMIT 3")
            sample = [f"/*\n3 rows from {relation}:\n" + "\t".join(sample_columns)]
            sample.extend("\t".join(str(value) for value in row) for row in rows)
            sample.append("*/")
            sections.append(schema + "\n\n" + "\n".join(sample))
        return "\n\n".join(sections)


def _token_usage(messages: list) -> dict[str, int]:
    """Tokens actually spent on one question, summed over the agent loop.

    Summed, not taken from the last message: a tool-calling agent makes several
    model calls per question, and reading only the final one undercounts the
    expensive part — the loop — by however many turns it took.

    Best-effort by construction. Providers disagree about where usage lives and
    some omit it entirely, so an absent count is reported as zero rather than
    guessed from message length. A meter that estimates is a meter that will be
    quoted as if it measured.
    """
    total = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    for m in messages:
        usage = getattr(m, "usage_metadata", None)
        if not isinstance(usage, dict):
            meta = getattr(m, "response_metadata", None) or {}
            usage = meta.get("token_usage") or meta.get("usage")
        if not isinstance(usage, dict):
            continue
        got_in = usage.get("input_tokens", usage.get("prompt_tokens"))
        got_out = usage.get("output_tokens", usage.get("completion_tokens"))
        if got_in is None and got_out is None:
            continue
        total["input_tokens"] += int(got_in or 0)
        total["output_tokens"] += int(got_out or 0)
        total["calls"] += 1
    total["total_tokens"] = total["input_tokens"] + total["output_tokens"]
    return total


def _message_text(message: Any) -> str:
    """Normalize LangChain message content without assuming one provider shape."""

    value = getattr(message, "text", None)
    if isinstance(value, str) and value:
        return value.strip()
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "\n".join(chunks).strip()
    # Unknown SDK objects can include request metadata in their repr. Treat an
    # unrecognized shape as empty instead of serializing it into a public answer.
    return ""


def build_sql_tools(db: FinanceSQLDatabase, llm: Any) -> list[Any]:
    """Build the four tools in LangChain's current SQL-agent guide."""

    @tool
    def sql_db_list_tables() -> str:
        """Input is empty; output is the comma-separated list of available relations."""

        return ", ".join(db.get_usable_table_names())

    @tool
    def sql_db_schema(table_names: str) -> str:
        """Return schema and sample rows for a comma-separated list of available relations."""

        try:
            return db.get_table_info(name.strip() for name in table_names.split(","))
        except SQLPolicyError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            print("SQL schema lookup failed "
                  f"({type(exc).__name__}); no exception detail logged")
            return "Error: schema lookup failed"

    @tool
    def sql_db_query(query: str) -> str:
        """Execute one SELECT query; return rows or an error that the agent can correct."""

        try:
            return db.run(query)
        except SQLPolicyError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            print("SQL query execution failed "
                  f"({type(exc).__name__}); no exception detail logged")
            return "Error: query execution failed"

    @tool
    def sql_db_query_checker(query: str) -> str:
        """Double-check a query before executing it with sql_db_query."""

        trigger_prompt = f"""{query}
Double check the {db.dialect} query above for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins

If there are any of the above mistakes, rewrite the query. If there are no mistakes, just reproduce the original query.

Output the final SQL query only.

SQL Query:"""
        return _message_text(llm.invoke(trigger_prompt))

    return [sql_db_list_tables, sql_db_schema, sql_db_query, sql_db_query_checker]

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
   - operating_spend (all funds total operating expenditures — what it costs
     to RUN the schools). This is NOT total_spend. total_spend additionally
     contains bond-funded construction and debt service, so for a district
     mid-build the two differ enormously: Tioga ISD in 2014 spent $3,205,610
     operating against $5,603,166 all-funds. Reporting one as the other
     overstates the cost of running a district by up to 75%.

   The sixteen PEIMS function codes — what the money was spent ON. These sum
   to operating_spend, so a share must be taken against operating_spend and
   never against total_spend:
   - instruction_spend (fct 11,95 — teachers and the classroom)
   - library_media_spend (12), curriculum_staff_dev_spend (13)
   - instructional_leadership_spend (21), campus_admin_spend (23 — principals)
   - counseling_spend (31), social_work_spend (32), health_services_spend (33)
   - transportation_spend (34 — buses), food_service_spend (35 — meals)
   - extracurricular_spend (36 — athletics, band, UIL)
   - general_admin_spend (41,92 — superintendent, business office, board)
   - plant_maintenance_spend (51 — utilities, custodians, upkeep)
   - security_spend (52), data_processing_spend (53), community_services_spend (61)

   What the money was bought AS:
   - payroll_spend, contracted_services_spend, supplies_spend

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
- When asked about "spending", use total_spend unless specified otherwise.
  But "operating spend", "operating expenditures", "cost of running the
  district", or "spending excluding construction and debt" ALL mean the
  operating_spend column. Never answer one of those with total_spend, and
  never describe total_spend as operating. If a question is ambiguous
  between them, give the figure you used and name the column it came from.
- A NULL function column means the district did not report that function,
  which usually means it does not run it. Never report it as $0 and never
  say a district "spends nothing on" it — say it reports none. Use
  WHERE col IS NOT NULL when ranking, or the districts that report nothing
  will rank as the thriftiest in Texas.
- Any share or percentage of a function is a share of operating_spend. Never
  divide a function by total_spend.
- Per-student figures for a tiny district are noise: one bus in a 40-student
  district reads as an extraordinary transport budget. When ranking on a
  per-student function figure, require enrollment >= 100 and say you did.
- For year ranges, use BETWEEN operator

Be concise and clear in your responses. If asked for trends, calculate year-over-year changes.

How to write the answer (the interface applies the presentation, so write for
meaning and let the layout happen downstream):
- FIRST SENTENCE IS THE ANSWER. Lead with the number or the finding, in plain
  words. No preamble, no "Based on the data", no restating the question.
- NAME THE FISCAL YEAR of every figure. A number without a year reads as
  "now" and the data ends at fiscal 2025. Say "in fiscal 2024", not "currently".
- Keep it under about 150 words unless the question asks for a list. If a
  result is long, SHOW the first several rows and say how many there are in
  total. That is a limit on what you DISPLAY, never on what you query — the
  counting rule above still governs the SQL, and a count must come from
  COUNT(), never from how many rows you chose to print.
- Use a plain pipe table only when comparing the same measure across rows.
  Use **bold** for the figures that matter. Do not use headings for a short
  answer, and never write a "Sources:" or "Note:" trailer — the interface
  attaches sources, limitations and follow-up questions itself.
- Explain what the number MEANS in one sentence when a reader would otherwise
  have to guess: whether it is high or low, and against what.
- If the data cannot answer the question, say exactly that and say what it
  does cover. Never estimate a figure that is not in the views above."""


class TexasFinanceNLPEngine:
    """Natural language query engine for Texas school finance data"""

    def __init__(
        self,
        db_url: Optional[str] = None,
        llm: Optional[Any] = None,
        db: Optional[FinanceSQLDatabase] = None,
    ):
        if db is None:
            # NLP_DB_URL is the least-privilege role from sql/create_nlp_role.sql:
            # SELECT on the two public views, read-only transactions, nothing
            # else. Do not fall back to SUPABASE_DB_URL: relation discovery is
            # not authorization, and model-authored SQL must fail closed rather
            # than run as the database owner.
            db_url = db_url or os.getenv("NLP_DB_URL")
            if not db_url:
                raise ValueError("NLP_DB_URL not found in environment")
            # Connect to the two public read-only views only (least privilege)
            db = FinanceSQLDatabase.from_uri(
                db_url,
                include_relations=NLP_RELATIONS,
            )
        cfg = resolve_llm_config()
        if llm is None and not cfg.configured:
            raise ValueError(
                f"{cfg.key_env_name} not found in environment variables "
                f"(provider: {cfg.provider})"
            )

        self.db = db

        # DeepSeek speaks the OpenAI protocol, so the same client class serves
        # both providers — only base_url and the model name differ. See
        # src/llm_config.py for how the provider is chosen.
        if llm is None:
            kwargs = {
                "model": cfg.model,
                "temperature": cfg.temperature,
                "api_key": cfg.api_key,
            }
            if cfg.base_url:
                kwargs["base_url"] = cfg.base_url
            llm = ChatOpenAI(**kwargs)
        self.llm = llm

        self.tools = build_sql_tools(self.db, self.llm)
        self.agent = create_agent(
            self.llm,
            self.tools,
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
            output = _message_text(messages[-1]) if messages else "No result returned"

            return {
                "success": True,
                "answer": output,
                "question": question,
                "usage": _token_usage(messages),
            }

        except Exception as exc:
            # Model/provider exceptions can echo request metadata, endpoint
            # credentials, or generated SQL. /query is public and its error is
            # also stored in chat_turn, so never return raw exception text.
            print("NLP query failed "
                  f"({type(exc).__name__}); no exception detail logged")
            return {
                "success": False,
                "error": "The question could not be answered. Please try again.",
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
