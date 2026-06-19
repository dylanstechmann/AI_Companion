# AI Companion - Phase 3: Multi-Agent, Skills, Browser Control

COST TIER: Top-tier model (these are complex architectural tasks)
COMPLEXITY: High
PREREQUISITES: Phase 1 + 2 complete

---

## Task 1: Multi-Agent Orchestration

### Goal
Enable the AI to spawn and coordinate multiple sub-agents that work in parallel on complex tasks. For example: "Research competitor products, write a report, and create a presentation" should spawn 3 agents working simultaneously.

### Architecture

```
User Request
     |
     v
[Orchestrator Agent]
     |
     +---> [Research Agent] ---> ChromaDB results
     |
     +---> [Writer Agent] ---> Document output
     |
     +---> [Code Agent] ---> Execution results
     |
     v
[Orchestrator merges results]
     |
     v
Final Response to User
```

### Backend Implementation

**New file: backend/app/orchestrator.py**
```
class AgentOrchestrator:
    """Manages multiple concurrent AI agent tasks."""
    
    async def plan(self, user_request: str) -> list[AgentTask]:
        """Use LLM to decompose request into sub-tasks."""
        # Call LLM with a planning prompt
        # Parse response into structured AgentTask objects
        # Each task has: id, type, description, dependencies
    
    async def execute(self, tasks: list[AgentTask]) -> AsyncGenerator[str, None]:
        """Execute tasks respecting dependency order."""
        # Group tasks by dependency level
        # Execute independent tasks concurrently (asyncio.gather)
        # Feed dependent tasks the results of their dependencies
        # Stream progress updates to the user
    
    async def merge_results(self, results: dict) -> str:
        """Use LLM to synthesize all agent outputs into a coherent response."""
```

**New file: backend/app/agents.py**
```
class BaseAgent:
    """Base class for specialized agents."""
    name: str
    description: str
    tools: list  # subset of available tools
    system_prompt: str
    
class ResearchAgent(BaseAgent):
    """Web search + page reading + synthesis."""
    
class WriterAgent(BaseAgent):
    """Document creation, editing, formatting."""
    
class CodeAgent(BaseAgent):
    """Code generation and execution."""
    
class AnalysisAgent(BaseAgent):
    """Data analysis and visualization."""
```

**New routes:**
- POST /api/agents/orchestrate - Start a multi-agent task
- GET /api/agents/tasks/{task_id} - Check task status (SSE stream)
- POST /api/agents/tasks/{task_id}/cancel - Cancel a running task

### Frontend Changes

**New component: AgentPanel.jsx**
- Shows the orchestrator's plan as a visual task graph
- Each agent appears as a card with status (queued/running/done/failed)
- Live progress streaming per agent
- Ability to cancel individual agents
- Final merged result displayed in chat

---

## Task 2: Skill/Plugin System

### Goal
Allow users (and the AI itself) to create reusable "skills" - packaged tool definitions that extend the AI's capabilities. For example: "Create a skill that monitors my stock portfolio."

### Architecture

```
skills/
├── stock_monitor/
│   ├── skill.json          # Metadata: name, description, triggers, parameters
│   ├── handler.py          # Python implementation
│   └── requirements.txt    # Additional pip packages (installed at load time)
├── weather/
│   ├── skill.json
│   └── handler.py
└── calendar_sync/
    ├── skill.json
    └── handler.py
```

### Backend Implementation

**New file: backend/app/skills.py**
```
class SkillManager:
    """Discovers, loads, and manages user-defined skills."""
    
    def __init__(self, skills_dir: str = "/app/data/skills"):
        self.skills_dir = skills_dir
        self.loaded_skills = {}
    
    def discover(self) -> list[SkillMetadata]:
        """Scan skills directory for skill.json files."""
    
    def load(self, skill_name: str) -> Skill:
        """Dynamically import and register a skill."""
    
    def unload(self, skill_name: str):
        """Remove a skill from active use."""
    
    def get_tools_schema(self) -> list[dict]:
        """Generate OpenAI function-calling schema for all loaded skills."""
    
    async def execute(self, skill_name: str, function_name: str, args: dict) -> Any:
        """Execute a skill's function."""
    
    async def create_skill(self, name: str, description: str, code: str) -> SkillMetadata:
        """AI-generated skill: write skill.json + handler.py, validate, and load."""
```

**skill.json format:**
```json
{
  "name": "stock_monitor",
  "description": "Monitor stock prices and send alerts",
  "version": "1.0.0",
  "author": "user",
  "functions": [
    {
      "name": "get_stock_price",
      "description": "Get current price for a stock ticker",
      "parameters": {
        "type": "object",
        "properties": {
          "ticker": {"type": "string", "description": "Stock ticker symbol"}
        },
        "required": ["ticker"]
      }
    }
  ],
  "triggers": ["stock", "price", "portfolio", "market"],
  "requirements": ["yfinance"]
}
```

**Integration with LLM:**
- SkillManager.get_tools_schema() is merged with the existing TOOLS_SCHEMA
- When a skill tool is called, it routes to SkillManager.execute() instead of TOOL_DISPATCH
- Skills can have their own pip requirements (installed in an isolated venv)

### Frontend Changes

**New component: SkillsPanel.jsx**
- List of installed skills with enable/disable toggles
- "Create New Skill" form (name, description, code editor)
- "AI Create Skill" button - describe what you want and the AI writes it
- Skill marketplace (future: browse community skills)

---

## Task 3: Web Browser Control

### Goal
Give the AI the ability to control a web browser to:
- Navigate to URLs and read page content (already partially done via read_webpage tool)
- Fill forms, click buttons, extract data
- Take screenshots and analyze them with vision
- Automate repetitive web tasks

### Architecture

**Option A: Playwright (Recommended)**
- Headless Chromium runs inside the Docker container
- Full browser automation: click, type, scroll, screenshot, PDF
- Can handle SPAs and JavaScript-rendered content

**Option B: Puppeteer**
- Similar to Playwright but Node.js based
- Would require running a sidecar Node service

### Backend Implementation

**New file: backend/app/browser.py**
```
class BrowserService:
    """Manages a headless browser for web automation."""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
    
    async def start(self):
        """Launch headless Chromium."""
    
    async def navigate(self, url: str) -> dict:
        """Navigate to URL, return page title and text content."""
    
    async def screenshot(self, url: str = None) -> bytes:
        """Take a screenshot of the current page (or navigate first)."""
    
    async def click(self, selector: str) -> dict:
        """Click an element by CSS selector."""
    
    async def type_text(self, selector: str, text: str) -> dict:
        """Type text into an input field."""
    
    async def extract(self, selectors: dict) -> dict:
        """Extract text/attributes from multiple selectors."""
    
    async def execute_js(self, script: str) -> Any:
        """Run JavaScript in the page context."""
    
    async def fill_form(self, form_data: dict) -> dict:
        """Fill a form with the given field:value pairs."""
    
    async def close(self):
        """Close the browser."""
```

**New tools for tools.py:**
```python
# Add to TOOLS_SCHEMA and TOOL_DISPATCH:
- browse_webpage(url): Navigate and return content + screenshot
- click_element(selector): Click a page element
- fill_form(url, form_data): Navigate to URL and fill a form
- take_screenshot(): Screenshot current page, return as base64
```

**Docker changes:**
- Add playwright and chromium to the backend Dockerfile:
```dockerfile
RUN pip install playwright && playwright install chromium --with-deps
```

### Frontend Changes

**New component: BrowserView.jsx**
- Shows screenshots from the browser in real-time
- Overlay with clickable hotspots that the AI highlights
- "Watch mode": shows what the AI is doing in the browser step by step

### Security Considerations
- Sandbox the browser: no access to local filesystem
- Rate limit navigation
- Block access to internal Docker network
- User confirmation for sensitive actions (form submissions, purchases)
- Timeout for long-running browser sessions

---

## Acceptance Criteria

### Multi-Agent:
- [ ] Orchestrator can decompose complex requests into sub-tasks
- [ ] Sub-agents execute concurrently
- [ ] Progress streams to frontend in real-time
- [ ] Results are merged into a coherent response
- [ ] Individual agents can be cancelled

### Skills:
- [ ] Skills can be created from the UI
- [ ] AI can create skills autonomously
- [ ] Skills are persisted and loaded on restart
- [ ] Skills integrate with the tool-calling system
- [ ] Skills can have pip dependencies

### Browser:
- [ ] AI can navigate to URLs and read content
- [ ] AI can take and analyze screenshots
- [ ] AI can fill forms and click elements
- [ ] Browser actions are sandboxed and rate-limited
- [ ] Screenshots stream to frontend
