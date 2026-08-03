"""The MCP tool surface: declarative records, and everything generated from them.

`registry.py` holds the record types and the generators; `tools.py` declares
the five tools; `bindings.py` says which service method answers each action;
`server.py` wires them onto an MCP server. The split is the point — an action
record that decides something is visibly in the wrong file.
"""
