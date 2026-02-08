# Session Behavior Analysis

## Test Results Summary

| Scenario | Sessions | Invocations | Method |
|----------|----------|-------------|--------|
| 1. Explicit session context | 2 | 6 | `client.session()` |
| 2. Without session + header | 2 | 15 | `client.get_tools()` + header |
| 3. Without session, no header | 4 | 15 | `client.get_tools()` |

## Explanation

### Scenario 1: `run_agent_with_prompts_single_session()` - 2 sessions, 6 invocations

**Why 2 sessions?**
- MultiServerMCPClient internally creates connections for different purposes
- Even within `async with client.session()`, it may create:
  - 1 session for the initial `list_tools` call
  - 1 session for subsequent tool executions
- The session context manager provides **logical** session management but may still use multiple **physical** connections

**Why 6 invocations?**
- 1 invocation: `list_tools` to load available tools
- 3 invocations: One tool call per prompt (add_numbers, multiply_numbers, greet_users)
- 2 additional invocations: Possibly `initialize` calls per session
- Total: ~6 invocations

This is the **most efficient** approach because the explicit session reuses connections.

---

### Scenario 2: `run_agent_without_session()` with `Mcp-Session-Id` header - 2 sessions, 15 invocations

**Why 2 sessions despite the header?**
- The `Mcp-Session-Id` header is being respected! That's why you still see only 2 sessions instead of more
- However, MultiServerMCPClient still creates separate connections for:
  - Tool discovery/listing
  - Tool execution
- The header ensures these connections report the same session ID to the server

**Why 15 invocations?**
- Without explicit session management, `client.get_tools()` creates ephemeral connections
- Each tool call through the agent may:
  - Open a new connection
  - Initialize/handshake (2 invocations per connection)
  - Call the tool (1 invocation)
  - Close
- 3 prompts × ~5 invocations each = 15 invocations
- The overhead comes from repeated initialization/teardown

---

### Scenario 3: `run_agent_without_session()` without header - 4 sessions, 15 invocations

**Why 4 sessions?**
- Without the `Mcp-Session-Id` header, **each connection gets its own session ID**
- MultiServerMCPClient creates multiple connections:
  - 1 for initial `get_tools()`
  - 1+ for tool executions (possibly one per prompt or tool call group)
- Result: 4 separate sessions created

**Why still 15 invocations?**
- Same connection pattern as Scenario 2
- The difference is only in **session isolation**, not in the number of API calls
- Each connection still needs initialization/handshake/tool calls

---

## Key Insights

### 1. **Explicit Session Management is Most Efficient**
```python
async with client.session("agentcore") as session:
    # All operations share the same connection
    # Minimal overhead: ~6 invocations for 3 prompts
```

### 2. **The `Mcp-Session-Id` Header Works**
- It reduces sessions from 4 → 2
- But it doesn't reduce invocations (15 remains 15)
- It provides **session continuity** but not **connection reuse**

### 3. **Why Headers Don't Fully Consolidate Sessions**
MultiServerMCPClient's architecture:
- Creates separate transport connections for different operation types
- Headers ensure the same session ID is used
- But connection pooling still creates distinct "sessions" from the server's perspective
- Some sessions may be for:
  - Tool listing
  - Tool execution  
  - Possibly parallel tool calls

### 4. **Invocation Overhead Without Explicit Sessions**
15 invocations vs 6 invocations = **2.5x overhead**
- Repeated connection setup/teardown
- Multiple protocol handshakes
- Potentially redundant tool listings

---

## Recommendations

### For Maximum Efficiency (Fewest Invocations)
Use explicit session management:
```python
async with client.session("agentcore") as session:
    tools = await load_mcp_tools(session, ...)
    # All tool calls reuse this session
```

### For Session Continuity (Same Session ID)
Use headers when explicit session management isn't possible:
```python
client = MultiServerMCPClient({
    "agentcore": {
        "headers": {"Mcp-Session-Id": session_id}
    }
})
```

### Understanding the Trade-offs
- **Explicit session**: Fewest invocations, best performance, single logical session
- **Headers only**: Session ID consistency, but more invocations due to connection overhead
- **No headers**: Multiple sessions, useful for true session isolation per operation

---

## Why This Matters

**Cost**: More invocations = more API calls = higher costs
**Performance**: More invocations = slower execution
**State**: If your MCP server maintains state, session management determines what state is shared
**Debugging**: Understanding session behavior helps troubleshoot issues with stateful tools
