"""Storage for the catalogue, reached only through the service layer.

`catalogue.py` names the contract and the records; `sqlite.py` is the
implementation behind it. Nothing above this package imports a backend
directly, which is what keeps replacing one a single-module change.
"""
