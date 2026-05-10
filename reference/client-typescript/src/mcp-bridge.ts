/**
 * SBP Surface MCP Bridge — L5 tool registration and dispatch.
 *
 * Surfaces declare local MCP tools in the ATTACH_SESSION frame.
 * When the gateway sends a TOOL_CALL frame, the bridge dispatches to
 * the registered handler and returns the result via TOOL_RESULT.
 *
 * This module is optional: import it only if your surface exposes local
 * MCP tools. The wire protocol (TOOL_CALL/TOOL_RESULT frames) is open;
 * this is the surface-side convenience wrapper.
 */

export type ToolHandler = (input: Record<string, unknown>) => Promise<unknown>;

export class MCPBridge {
  private _handlers = new Map<string, ToolHandler>();

  /**
   * Register a local MCP tool handler.
   *
   * @param name - Tool name (must match what you declare in mcp_tools at attach time)
   * @param handler - Async function that receives tool_input and returns the result
   */
  register(name: string, handler: ToolHandler): this {
    this._handlers.set(name, handler);
    return this;
  }

  /** Returns the list of registered tool names (for ATTACH_SESSION mcp_tools). */
  get toolNames(): string[] {
    return Array.from(this._handlers.keys());
  }

  /**
   * Dispatch a TOOL_CALL to the registered handler.
   * Returns { result } on success or { error } on failure.
   */
  async dispatch(
    toolName: string,
    toolInput: Record<string, unknown>
  ): Promise<{ result?: unknown; error?: string }> {
    const handler = this._handlers.get(toolName);
    if (!handler) {
      return { error: `Tool '${toolName}' is not registered on this surface` };
    }
    try {
      const result = await handler(toolInput);
      return { result };
    } catch (err) {
      return { error: err instanceof Error ? err.message : String(err) };
    }
  }
}
