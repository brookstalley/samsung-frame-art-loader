"""Bringing the 2024 wall's works into the catalogue, through the service layer.

This package is a *binding*, in the same sense the MCP tools are: it reads an
outside file, calls catalogue operations, and formats what came back. It enforces
no catalogue rule of its own — every work it creates goes through
`CatalogueService`, so a work that arrived from the old index obeys exactly the
constraints a work that arrived from discovery does. The rules it *does* hold are
its own: how to read one particular legacy file, and what to say about a record
that would not seed cleanly.
"""
