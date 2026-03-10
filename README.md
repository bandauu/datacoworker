
# 🔮 Data Coworker - 3-Agent Code Generation System

AI-powered SaaS analytics assistant using **code generation** with multi-agent collaboration.

## 🚀 Architecture: Planner → Reviewer → Interpreter

### 3 Specialized Agents:
1. **Code Planner** 📝 - Generates Python code (SQL + pandas)
2. **Code Reviewer** 🔍 - Enforces security & READ-ONLY access
3. **Results Interpreter** 💡 - Executes code & provides business insights

### Key Features:
- ✅ **Code Generation** - Python + SQL (more powerful than SQL strings)
- ✅ **READ-ONLY Enforcement** - 5-layer security system
- ✅ **RAG Integration** - Upload PDFs for context
- ✅ **Auto-Visualization** - Charts from any query
- ✅ **Business Insights** - Natural language explanations

## 🛡️ Security (5 Layers)

1. **Planner Instructions** - Trained to generate READ-ONLY code
2. **Code Reviewer (AST)** - Scans code structure for threats
3. **Code Reviewer (Keywords)** - Blocks DELETE/UPDATE/INSERT/DROP
4. **Executor Pre-check** - Final validation before running
5. **Sandboxed Environment** - Restricted Python builtins

**Result:** ZERO possibility of write operations ✅

## 🎯 Usage

```
User: "What's our MRR by plan?"

Planner: [Generates Python code with SQL query]
Reviewer: [Reviews code] "✅ Approved - no security issues"
Interpreter: [Executes & analyzes]

Output: "Your MRR breakdown: Enterprise $24,990 (66%), 
Professional $9,950 (26%), Starter $2,450 (8%).
Key insight: Enterprise drives 2/3 of revenue.
Recommended: Stacked bar chart."
```

## 📊 Why Code Generation > SQL Strings?

| Approach | Power | Security | Flexibility |
|----------|-------|----------|-------------|
| SQL Strings | Limited | Keyword filter | SQL only |
| **Code Generation** | **High** | **AST analysis** | **SQL + pandas** |

## 🏗️ Tech Stack

- **Framework:** CrewAI (sequential process)
- **LLM:** OpenAI GPT-4o & GPT-4o-mini
- **RAG:** LangChain + FAISS + sentence-transformers
- **UI:** Streamlit
- **DB:** SQLite (SaaS analytics demo data)
- **Viz:** Plotly

## 📝 Example Queries

- "What's our MRR by plan?"
- "Show customer churn rate"
- "Compare feature adoption rates"
- "Which industries have highest revenue?"
- "Find low-usage customers at churn risk"

## Prerequisites

- **Python 3.10, 3.11, or 3.12** (required for CrewAI and Streamlit). Check with `python3 --version`.
- If you have 3.9 or lower, install 3.11 (e.g. `brew install python@3.11`) and use it:
  ```bash
  python3.11 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  streamlit run app.py
  ```

## 🎓 Homework Compliance

✅ Multi-agent (3 agents with DISTINCT roles)  
✅ CrewAI framework  
✅ 3+ tools (inspect_schema, review_code, execute_code, search_documents)  
✅ RAG implementation (PDF/DOCX/TXT)  
✅ Engineering guardrails (5-layer security)  
✅ Design pattern (Plan → Review → Execute)  

**Advanced:** Code generation instead of simple SQL strings!

## 🚀 Deploy

This Space runs automatically on HuggingFace. No setup needed!

For local development (use a venv with Python 3.10+):
```bash
python3.11 -m venv .venv && source .venv/bin/activate   # or python3 if already 3.10+
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-your-key" > .env
streamlit run app.py
```

## 📄 License

MIT License - Educational project
