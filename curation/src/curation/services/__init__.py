"""The only home for operation logic.

Both external surfaces are bindings over this package: the MCP tools and the
HTTP handlers unpack arguments, call one method here, and format the result.
Parity between an agent and a click is therefore structural rather than
remembered.
"""
