"""
Data Coworker - Code Generation Edition
3-Agent System: Planner → Reviewer → Interpreter
"""
import os
import re
import sqlite3
import json
import time
import uuid
import ast
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Import modules
from rag_system import get_rag_system
from visualization import get_visualizer

# Import CrewAI
from crewai import Agent, Task, Crew, Process
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# ==================== CONFIGURATION ====================

st.set_page_config(
    page_title="Data Coworker - Code Generation",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);}
    h1, h2, h3 {color: #2d3748; font-weight: 600;}
    [data-testid="stMetricValue"] {font-size: 2rem; color: #667eea;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg, #2d3748 0%, #1a202c 100%);}
    [data-testid="stSidebar"] * {color: white !important;}
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border: none; border-radius: 8px;
        padding: 0.5rem 2rem; font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

# ==================== CONSTANTS ====================

DB_PATH = "database/saas_analytics.db"
MEMORY_PATH = "database/memory.json"
PROFILE_PATH = "database/user_profile.json"

DB_SCHEMA = """
Database: saas_analytics.db (SQLite)

Tables (use exact column names in SQL):
1. users: user_id, company_name, email, industry, signup_date, status
2. subscriptions: subscription_id, user_id, plan_name, mrr (Monthly Recurring Revenue - use 'mrr' not 'err'), start_date, end_date, status
3. usage_metrics: metric_id, user_id, feature_name, usage_count, date
4. revenue: transaction_id, user_id, amount, transaction_type, date
5. support_tickets: ticket_id, user_id, priority, status, created_date, resolved_date
6. feature_adoption: adoption_id, user_id, feature_name, first_used_date, total_usage
"""

# ==================== INITIALIZATION ====================

if 'initialized' not in st.session_state:
    st.session_state.initialized = False
    st.session_state.query_history = []

def check_database() -> Tuple[bool, str]:
    """Verify database exists and is readable. Returns (ok, message)."""
    if not os.path.exists(DB_PATH):
        return False, "File missing"
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        cursor.fetchone()
        conn.close()
        return True, "OK"
    except Exception as e:
        return False, str(e)


@st.cache_resource
def initialize_database():
    """Initialize database if needed"""
    if not os.path.exists(DB_PATH):
        from create_db import create_saas_database
        create_saas_database()
    return True

@st.cache_resource
def load_rag_system():
    return get_rag_system()

@st.cache_resource
def load_visualizer():
    return get_visualizer()

@st.cache_resource
def load_llm_models():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ OPENAI_API_KEY not found")
        return None, None
    
    gpt4 = ChatOpenAI(model="gpt-4o", temperature=0)
    gpt4_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return gpt4, gpt4_mini

# ==================== TOOLS ====================

def _extract_python_code(text: str) -> str:
    """Extract Python code from markdown blocks or return trimmed text if already code."""
    text = (text or "").strip()
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    if text.startswith("import ") or "sqlite3.connect" in text:
        return text
    return text


def _strip_whitelisted_imports(code: str) -> str:
    """Remove import lines for modules we inject into the sandbox (pd, sqlite3, numpy)."""
    allowed_imports = [
        "import pandas as pd", "import pandas", "import sqlite3", "import numpy as np", "import numpy"
    ]
    lines = code.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith("#"):
            out.append(line)
            continue
        skip = False
        for imp in allowed_imports:
            if stripped == imp or stripped.startswith(imp + " "):
                skip = True
                break
        if not skip:
            out.append(line)
    return "\n".join(out).strip()


@tool("Inspect Database Schema")
def inspect_schema_tool(table_name: str = "") -> str:
    """Get database schema information"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if table_name:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            result = {"table": table_name, "columns": [{"name": col[1], "type": col[2]} for col in columns]}
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            result = {"tables": tables, "schema": DB_SCHEMA}
        
        conn.close()
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool("Review Python Code")
def review_code_tool(code: str) -> str:
    """
    Review code for security and correctness.
    Enforces READ-ONLY database access.
    Pass either raw Python code or text containing a ```python ... ``` block.
    """
    code = _extract_python_code(code)
    if not code:
        return json.dumps({"approved": False, "issues": ["No Python code found to review."], "suggestions": []})
    issues = []
    suggestions = []
    
    try:
        tree = ast.parse(code)
        code_upper = code.upper()
        
        # CHECK 1: Block SQL write operations
        dangerous_sql = ['DELETE', 'UPDATE', 'INSERT', 'DROP', 'ALTER', 
                        'TRUNCATE', 'CREATE', 'REPLACE', 'GRANT', 'REVOKE']
        
        for keyword in dangerous_sql:
            if keyword in code_upper:
                issues.append(f"❌ BLOCKED: SQL {keyword} operation not allowed (READ-ONLY)")
        
        # CHECK 2: Block unauthorized imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in ['pandas', 'sqlite3', 'numpy']:
                        issues.append(f"❌ Import '{alias.name}' not allowed")
            
            # CHECK 3: Block dangerous functions
            if isinstance(node, ast.Call):
                if isinstance(node, ast.Name):
                    if node.id in ['eval', 'exec', 'open', '__import__', 'compile']:
                        issues.append(f"❌ Function '{node.id}' not allowed")
        
        # CHECK 4: SQL injection patterns
        if ('f"' in code or "f'" in code) and ('SELECT' in code_upper or 'WHERE' in code_upper):
            suggestions.append("⚠️ Avoid f-strings in SQL (use parameterized queries)")
        
        # CHECK 5: Database connection handling
        if 'sqlite3.connect' in code and 'conn.close()' not in code:
            suggestions.append("Add conn.close() to release connection")
        
        # CHECK 6: Result variable
        if 'result =' not in code:
            issues.append("❌ Code must assign output to 'result' variable")
        
        return json.dumps({
            "approved": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
            "security_level": "APPROVED" if len(issues) == 0 else "REJECTED"
        })
        
    except SyntaxError as e:
        return json.dumps({
            "approved": False,
            "issues": [f"Syntax error: {str(e)}"],
            "suggestions": []
        })

@tool("Execute Python Code")
def execute_code_tool(code: str) -> str:
    """
    Execute Python code in sandboxed READ-ONLY environment.
    Pass either raw Python code or text containing a ```python ... ``` block.
    """
    # Extract code if wrapped in markdown (e.g. from previous agent output)
    code = _extract_python_code(code)
    if not code:
        return json.dumps({"error": "No Python code found. Pass the code block from the planner/reviewer output."})
    # SAFETY: Pre-execution check
    code_upper = code.upper()
    dangerous_sql = ['DELETE', 'UPDATE', 'INSERT', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE', 'REPLACE']
    
    for keyword in dangerous_sql:
        if keyword in code_upper:
            return json.dumps({
                "error": f"🛡️ BLOCKED: {keyword} operation not allowed",
                "reason": "READ-ONLY system. Only SELECT queries permitted."
            })
    
    # Strip imports we provide in the sandbox so exec doesn't need __import__
    code = _strip_whitelisted_imports(code)
    # SAFETY: Restricted execution environment (pd, sqlite3 already in globals)
    safe_globals = {
        'pd': pd,
        'sqlite3': sqlite3,
        'DB_PATH': DB_PATH,
        '__builtins__': {
            'len': len, 'sum': sum, 'max': max, 'min': min, 'round': round,
            'abs': abs, 'str': str, 'int': int, 'float': float, 'bool': bool,
            'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
            'range': range, 'enumerate': enumerate, 'zip': zip,
            'sorted': sorted, 'reversed': reversed, 'print': print
        }
    }
    try:
        import numpy
        safe_globals['np'] = numpy
        safe_globals['numpy'] = numpy
    except ImportError:
        pass
    safe_locals = {}
    
    try:
        exec(code, safe_globals, safe_locals)
        
        if 'result' not in safe_locals:
            return json.dumps({"error": "Code must assign output to 'result' variable"})
        
        result = safe_locals['result']
        
        if isinstance(result, pd.DataFrame):
            return json.dumps({
                "success": True,
                "type": "dataframe",
                "rows": len(result),
                "columns": list(result.columns),
                "data": result.to_dict('records')[:100]
            })
        else:
            return json.dumps({
                "success": True,
                "type": "scalar",
                "value": str(result)
            })
            
    except Exception as e:
        return json.dumps({"error": f"Execution error: {str(e)}"})

@tool("Search Documents")
def search_documents_tool(query: str) -> str:
    """Search uploaded documents"""
    rag_system = load_rag_system()
    results = rag_system.search(query, k=3)
    return json.dumps({"results": results, "count": len(results)})

# ==================== AGENTS ====================

@st.cache_resource
def create_agents():
    """Create 3-agent system"""
    gpt4, gpt4_mini = load_llm_models()
    if not gpt4:
        return None
    
    # AGENT 1: Code Planner
    code_planner = Agent(
        role="Code Planner",
        goal="Generate Python code to answer data questions using SQL and pandas",
        backstory=f"""You are an expert data analyst who writes Python code.
        
        Database Schema:
        {DB_SCHEMA}
        
        CRITICAL: Generate ONLY READ-ONLY code. Never use DELETE/UPDATE/INSERT/DROP/ALTER.
        
        IMPORTANT: If the question is about the USER'S profile, interests, 
        or preferences (not about database data), you should NOT generate 
        database code. Instead, return a simple response acknowledging 
        the user context provided in the task.

        Code template:
        ```python
        import pandas as pd
        import sqlite3
        
        conn = sqlite3.connect('{DB_PATH}')
        query = "SELECT ... FROM ..."  # READ-ONLY queries only!
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Optional pandas transformations
        result = df
        ```
        
        Always:
        - Use SELECT queries only
        - Close database connections
        - Assign output to 'result' variable
        - Use parameterized queries for safety
        - Use exact column names from the schema (e.g. subscriptions has 'mrr' for revenue, not 'err').
        - Prefer producing the code in one go; use inspect_schema_tool only if you need table/column names.
        """,
        tools=[inspect_schema_tool, search_documents_tool],
        llm=gpt4,
        verbose=True,
        max_iter=10,
        allow_delegation=False
    )
    
    # AGENT 2: Code Reviewer
    code_reviewer = Agent(
        role="Code Security Reviewer",
        goal="Review code for security and correctness, enforce READ-ONLY access",
        backstory="""You are a security-focused code reviewer.
        
        Your job:
        1. Use review_code_tool to analyze code
        2. BLOCK any write operations (DELETE/UPDATE/INSERT/DROP/etc.)
        3. Check for SQL injection risks
        4. Verify logic correctness
        5. APPROVE or REJECT with clear feedback
        
        Output format:
        - APPROVED: "✅ Code approved. Safe to execute."
        - REJECTED: "❌ Code rejected. Issues: [list]. This is a READ-ONLY system."
        Verify SQL column names match the schema exactly (e.g. subscriptions has 'mrr' for revenue, not 'err').
        Use review_code_tool once with the code from the previous step, then output your verdict.
        """,
        tools=[review_code_tool],
        llm=gpt4_mini,
        verbose=True,
        max_iter=6,
        allow_delegation=False
    )
    
    # AGENT 3: Results Interpreter
    results_interpreter = Agent(
        role="Results Interpreter",
        goal="Execute code and provide business insights",
        backstory="""You are a business intelligence analyst.
        
        Your job:
        1. Execute approved code using execute_code_tool
        2. Analyze the results
        3. Generate natural language insights
        4. Suggest visualizations
        
        Output format:
        "📊 Analysis: [summary]
        
        💡 Key Insights:
        1. [insight 1]
        2. [insight 2]
        
        📈 Visualization: [recommendation]"
        Use execute_code_tool once with the approved code from the previous step, then summarize.
        """,
        tools=[execute_code_tool],
        llm=gpt4,
        verbose=True,
        max_iter=6,
        allow_delegation=False
    )
    
    return {
        'planner': code_planner,
        'reviewer': code_reviewer,
        'interpreter': results_interpreter
    }

# ==================== WORKFLOW ====================

def analyze_with_code_generation(question: str, use_rag: bool = True) -> Tuple[str, str, pd.DataFrame, List[str], List[Tuple[str, str]]]:
    """Main 3-agent workflow. Returns (answer, code, results_df, thinking_steps, agent_outputs)."""
    thinking_steps = []
    agent_outputs: List[Tuple[str, str]] = []  # (agent_name, output_text)
    q_lower = (question or "").strip().lower()
    # Profile/interests questions: answer directly from saved profile (no code generation)
    profile_keywords = ("interest", "my role", "my profile", "what are my", "what's my", "what is my", "my preferences")
    if any(k in q_lower for k in profile_keywords):
        profile = load_profile()
        if profile:
            interests_list = "\n".join(f"• {i}" for i in profile.get("interests", []))
            role = profile.get("role", "Not set")
            answer = f"**Role:** {role}\n\n**Interests:**\n{interests_list}"
            steps = ["📝 Profile lookup", "✅ Done"]
            return answer, "", pd.DataFrame(), steps, []
        return "No profile set yet. Go to **Settings** to set your role and interests.", "", pd.DataFrame(), ["📝 Profile lookup", "⚠️ No profile"], []
    
    agents = create_agents()
    
    if not agents:
        return "Error: Agents not initialized", "", pd.DataFrame(), ["❌ LLM models not available"], []
    
    try:
        # Build context
        user_context = ""
        profile = load_profile()
        if profile:
            user_context += f"\nUser Role: {profile['role']}"
            user_context += f"\nUser Interests: {', '.join(profile['interests'])}"
        
        memories = load_memories()
        if memories:
            user_context += "\n\nUser Context:"
            for mem in memories[-3:]:
                user_context += f"\n- {mem['content']}"
        
        # Task 1: Code Planner
        plan_context = f"""Generate Python code to answer: {question}
        {user_context}
        """
        if use_rag:
            plan_context += "\n\nSearch documents if relevant using search_documents_tool."
        
        task1 = Task(
            description=plan_context,
            agent=agents['planner'],
            expected_output="Complete Python code in a ```python code block"
        )
        thinking_steps.append("📝 Code Planner: Generating solution...")
        
        # Task 2: Code Reviewer (context=task1 so it receives the planner's code)
        task2 = Task(
            description="""Review the code from the previous task using review_code_tool.
            Pass that code (or the ```python block from it) into the tool. Check for security and READ-ONLY compliance.
            Output APPROVED or REJECTED with brief feedback.""",
            agent=agents['reviewer'],
            context=[task1],
            expected_output="Security review with APPROVED/REJECTED status"
        )
        thinking_steps.append("🔍 Code Reviewer: Checking security...")
        
        # Task 3: Results Interpreter (context=task1,task2 so it receives planner code and review)
        task3 = Task(
            description="""Execute the code from the first task using execute_code_tool (pass the ```python block or code from the planner's output).
            Then summarize the results and provide brief business insights.""",
            agent=agents['interpreter'],
            context=[task1, task2],
            expected_output="Executed results with insights"
        )
        thinking_steps.append("💡 Results Interpreter: Analyzing data...")
        
        # Execute workflow
        crew = Crew(
            agents=[agents['planner'], agents['reviewer'], agents['interpreter']],
            tasks=[task1, task2, task3],
            process=Process.sequential,
            verbose=False
        )
        
        result = crew.kickoff()
        thinking_steps.append("✅ Workflow complete")
        
        # Collect each agent's output for the Agent Workflow section
        step_names = ["Code Planner", "Code Reviewer", "Results Interpreter"]
        for i, task in enumerate(crew.tasks):
            name = step_names[i] if i < len(step_names) else (getattr(task.agent, "role", None) or f"Task {i+1}")
            raw = ""
            if getattr(task, "output", None) and getattr(task.output, "raw_output", None):
                raw = (task.output.raw_output or "").strip()
            agent_outputs.append((name, raw or "(no output)"))
        
        result_str = str(result)
        
        # --- Extract code from Code Planner output (or fallback to result_str) ---
        planner_raw = agent_outputs[0][1] if agent_outputs and len(agent_outputs) > 0 else ""
        generated_code = _extract_python_code(planner_raw) if planner_raw and planner_raw != "(no output)" else ""
        if not generated_code:
            code_match = re.search(r'```python\n(.*?)\n```', result_str, re.DOTALL)
            if not code_match:
                code_match = re.search(r'```\n(.*?)\n```', result_str, re.DOTALL)
            generated_code = code_match.group(1).strip() if code_match else ""
        if not generated_code:
            generated_code = "Code not displayed"
        
        # --- Review and execute code ourselves; build results_df from execution output ---
        results_df = pd.DataFrame()
        if generated_code != "Code not displayed":
            try:
                review_res = review_code_tool.invoke({"code": generated_code})
                review_json = json.loads(review_res)
                if not review_json.get("approved", False):
                    issues = review_json.get("issues", [])
                    result_str += "\n\n❌ **Code rejected by security review:** " + "; ".join(issues)
                else:
                    exec_res = execute_code_tool.invoke({"code": generated_code})
                    exec_json = json.loads(exec_res)
                    if exec_json.get("success") and exec_json.get("type") == "dataframe" and "data" in exec_json:
                        results_df = pd.DataFrame(exec_json["data"])
                    elif exec_json.get("success") and exec_json.get("type") == "scalar":
                        result_str += "\n\n📌 **Result:** " + str(exec_json.get("value", ""))
                    elif "error" in exec_json:
                        result_str += "\n\n❌ **Execution error:** " + str(exec_json["error"])
            except json.JSONDecodeError as e:
                result_str += "\n\n❌ **Invalid response from execution:** " + str(e)
            except Exception as e:
                result_str += "\n\n❌ **Execution failed:** " + str(e)
        
        # If agent hit iteration/time limit, prepend a short note so user can retry
        if "iteration limit or time limit" in result_str.lower():
            result_str = (
                "⚠️ The agent stopped early (iteration/time limit). "
                "You can try again; iteration limits have been increased for longer runs.\n\n"
            ) + result_str
        return result_str, generated_code, results_df, thinking_steps, agent_outputs
        
    except Exception as e:
        thinking_steps.append(f"❌ Error: {str(e)}")
        return f"Error: {str(e)}", "", pd.DataFrame(), thinking_steps, []

# ==================== HELPER FUNCTIONS ====================

def load_profile():
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, 'r') as f:
            return json.load(f)
    return None

def save_profile(role, interest1, interest2, interest3):
    profile = {
        "role": role,
        "interests": [interest1, interest2, interest3],
        "created_at": datetime.now().isoformat()
    }
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, 'w') as f:
        json.dump(profile, f)

def load_memories():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, 'r') as f:
            return json.load(f)
    return []

def save_memory(content, shared=True):
    memories = load_memories()
    memories.append({
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "shared": shared
    })
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, 'w') as f:
        json.dump(memories, f)

def load_alerts():
    alerts_path = "database/alerts_config.json"
    if os.path.exists(alerts_path):
        with open(alerts_path, 'r') as f:
            return json.load(f)
    return []

def save_alert(alert_config):
    alerts_path = "database/alerts_config.json"
    alerts = load_alerts()
    alerts.append(alert_config)
    os.makedirs(os.path.dirname(alerts_path), exist_ok=True)
    with open(alerts_path, 'w') as f:
        json.dump(alerts, f, indent=2)

def delete_alert(alert_id):
    alerts_path = "database/alerts_config.json"
    alerts = load_alerts()
    alerts = [a for a in alerts if a.get('id') != alert_id]
    with open(alerts_path, 'w') as f:
        json.dump(alerts, f, indent=2)

# ==================== UI PAGES ====================

def render_sidebar():
    with st.sidebar:
        st.markdown("# 🔮 Data Coworker")
        st.markdown("### Code Generation Edition")
        st.markdown("---")
        
        page = st.radio(
            "Navigation",
            ["📊 Analytics", "📄 Documents", "🔔 Alerts", "💭 Memories", "⚙️ Settings"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.markdown("### System Status")
        db_ok, db_msg = check_database()
        checks = {
            "Database": (db_ok, db_msg if not db_ok else None),
            "OpenAI API": (os.environ.get("OPENAI_API_KEY") is not None, None),
            "RAG System": (True, None),
        }
        for name, (status, detail) in checks.items():
            if status:
                st.success(f"✅ {name}")
            else:
                st.error(f"❌ {name}" + (f" — {detail}" if detail else ""))
        
        st.markdown("---")
        profile = load_profile()
        if profile:
            st.markdown(f"**👤 Role:** {profile['role']}")
            st.markdown(f"**🎯 Interests:**")
            for interest in profile['interests']:
                st.markdown(f"• {interest}")
        
        return page

def render_analytics_page():
    st.title("🔮 Data Analytics - Code Generation")
    st.markdown("Ask questions and get Python code + insights")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        question = st.text_input(
            "Your Question",
            placeholder="What's our MRR by plan? | Show customer churn trend | Compare feature adoption",
            label_visibility="collapsed",
            key="query_input"
        )
    
    with col2:
        use_rag = st.checkbox("Use Docs", value=True)
    
    if st.button("🔍 Analyze", type="primary", use_container_width=True):
        if not question:
            st.warning("Please enter a question")
        else:
            with st.spinner("🤖 3-Agent workflow running..."):
                start_time = time.time()
                answer, code, results, thinking, agent_outputs = analyze_with_code_generation(question, use_rag)
                execution_time = time.time() - start_time
                
                st.session_state.query_history.append({
                    "question": question,
                    "timestamp": datetime.now().isoformat(),
                    "execution_time": execution_time
                })
                
                st.markdown("---")
                st.markdown("### 💬 Analysis")
                st.info(answer)
                st.caption(f"⏱️ Executed in {execution_time:.2f}s")
                
                if not results.empty:
                    st.markdown("### 📊 Results")
                    st.dataframe(results, use_container_width=True)
                    
                    st.markdown("### 📈 Visualization")
                    visualizer = load_visualizer()
                    fig = visualizer.auto_visualize(results, question)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                
                with st.expander("🔍 Generated Code"):
                    st.code(code, language="python")
                
                with st.expander("🧠 Agent Workflow"):
                    for step in thinking:
                        st.text(step)
                    if agent_outputs:
                        st.markdown("---")
                        st.markdown("**Each agent's output:**")
                        for agent_name, output_text in agent_outputs:
                            st.markdown(f"**📌 {agent_name}**")
                            display = output_text if output_text != "(no output)" else "No output captured."
                            st.text(display)
                            st.markdown("")
    
    st.markdown("---")
    st.markdown("### 💡 Example Questions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💰 MRR by Plan"):
            st.session_state.query_input = "What's our MRR by plan?"
    with col2:
        if st.button("👥 Churn Rate"):
            st.session_state.query_input = "What's our customer churn rate?"
    with col3:
        if st.button("📈 Feature Adoption"):
            st.session_state.query_input = "Show feature adoption rates"

def render_documents_page():
    st.title("📄 Document Library")
    st.markdown("Upload documents for RAG search")
    
    uploaded_file = st.file_uploader(
        "Upload Document",
        type=['pdf', 'txt', 'docx']
    )
    
    if uploaded_file:
        with st.spinner("📥 Processing..."):
            upload_dir = "database/uploads"
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, uploaded_file.name)
            
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            rag_system = load_rag_system()
            
            if uploaded_file.name.endswith('.pdf'):
                result = rag_system.process_pdf(file_path, uploaded_file.name)
            elif uploaded_file.name.endswith('.txt'):
                result = rag_system.process_text(file_path, uploaded_file.name)
            elif uploaded_file.name.endswith('.docx'):
                result = rag_system.process_docx(file_path, uploaded_file.name)
            
            if 'error' in result:
                st.error(f"❌ {result['error']}")
            else:
                st.success(f"✅ Indexed {uploaded_file.name} ({result.get('chunks', 0)} chunks)")
    
    st.markdown("---")
    st.markdown("### 📚 Indexed Documents")
    
    rag_system = load_rag_system()
    docs = rag_system.list_documents()
    
    if docs:
        for doc in docs:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{doc['filename']}**")
            with col2:
                st.text(f"{doc.get('chunks', 0)} chunks")
            with col3:
                st.text(f"{doc.get('pages', 'N/A')} pages")
    else:
        st.info("No documents indexed yet")

def render_alerts_page():
    st.title("🔔 Alert Management (Mockup)")
    st.markdown("Configure custom alerts - Feature preview")
    
    st.markdown("---")
    st.markdown("### ➕ Create New Alert")
    
    with st.form("new_alert_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            alert_name = st.text_input("Alert Name", placeholder="e.g., High Churn Risk")
            alert_metric = st.selectbox("Metric", ["MRR", "Churn Rate", "Urgent Tickets", "Low Usage", "Revenue Growth"])
            alert_condition = st.selectbox("Condition", ["Greater than", "Less than", "Equal to"])
        
        with col2:
            alert_threshold = st.number_input("Threshold", min_value=0.0, value=5.0)
            alert_frequency = st.selectbox("Frequency", ["Real-time", "Hourly", "Daily", "Weekly"])
            
            st.markdown("#### 📬 Channels")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                slack = st.checkbox("💬 Slack")
            with c2:
                email = st.checkbox("📧 Email", value=True)
            with c3:
                teams = st.checkbox("👥 Teams")
            with c4:
                webhook = st.checkbox("🔗 Webhook")
        
        if st.form_submit_button("✨ Create Alert", type="primary", use_container_width=True):
            if alert_name:
                alert_config = {
                    "id": str(uuid.uuid4())[:8],
                    "name": alert_name,
                    "metric": alert_metric,
                    "condition": alert_condition,
                    "threshold": alert_threshold,
                    "frequency": alert_frequency,
                    "channels": {"slack": slack, "email": email, "teams": teams, "webhook": webhook},
                    "status": "active",
                    "created_at": datetime.now().isoformat()
                }
                save_alert(alert_config)
                st.success(f"✅ Alert '{alert_name}' created!")
                st.rerun()
    
    st.markdown("---")
    st.markdown("### 📋 Configured Alerts")
    
    alerts = load_alerts()
    if alerts:
        for alert in alerts:
            with st.expander(f"🔔 {alert['name']} ({alert['status'].upper()})"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Metric:** {alert['metric']}")
                    st.markdown(f"**Condition:** {alert['condition']} {alert['threshold']}")
                    st.markdown(f"**Frequency:** {alert['frequency']}")
                with col2:
                    if st.button("🗑️ Delete", key=f"delete_{alert['id']}"):
                        delete_alert(alert['id'])
                        st.rerun()
    else:
        st.info("No alerts configured yet")
    
    st.caption("🔮 Mockup Feature: Integrations coming soon")

def render_memories_page():
    st.title("💭 Memory Management")
    
    new_memory = st.text_input("Add a new memory")
    if st.button("💾 Save Memory"):
        if new_memory:
            save_memory(new_memory)
            st.success("✅ Saved!")
            st.rerun()
    
    st.markdown("---")
    st.markdown("### 🧠 Stored Memories")
    
    memories = load_memories()
    if memories:
        for i, mem in enumerate(reversed(memories)):
            with st.expander(f"Memory {len(memories) - i}: {mem['content'][:50]}..."):
                st.markdown(f"**Content:** {mem['content']}")
                st.caption(f"Created: {mem['timestamp']}")
    else:
        st.info("No memories yet")

def render_settings_page():
    st.title("⚙️ Settings")
    
    profile = load_profile()
    
    with st.form("profile_form"):
        role = st.selectbox(
            "Role",
            ["Data Analyst", "Product Manager", "Executive", "Engineer", "Finance", "Marketing"],
            index=0 if not profile else ["Data Analyst", "Product Manager", "Executive", "Engineer", "Finance", "Marketing"].index(profile['role']) if profile else 0
        )
        
        st.markdown("### 🎯 Top 3 Interests")
        interests_options = ["Revenue & MRR", "Customer Churn", "Product Usage", "Support Metrics", "Growth Analytics", "Forecasting"]
        
        interest1 = st.selectbox("Primary", interests_options, index=0 if not profile else interests_options.index(profile['interests'][0]) if profile else 0)
        interest2 = st.selectbox("Secondary", interests_options, index=1 if not profile else interests_options.index(profile['interests'][1]) if profile else 1)
        interest3 = st.selectbox("Third", interests_options, index=2 if not profile else interests_options.index(profile['interests'][2]) if profile else 2)
        
        if st.form_submit_button("💾 Save Profile", type="primary"):
            save_profile(role, interest1, interest2, interest3)
            st.success("✅ Profile saved!")
            st.rerun()

# ==================== MAIN ====================

def main():
    initialize_database()
    current_page = render_sidebar()
    
    if current_page == "📊 Analytics":
        render_analytics_page()
    elif current_page == "📄 Documents":
        render_documents_page()
    elif current_page == "🔔 Alerts":
        render_alerts_page()
    elif current_page == "💭 Memories":
        render_memories_page()
    elif current_page == "⚙️ Settings":
        render_settings_page()

if __name__ == "__main__":
    main()
