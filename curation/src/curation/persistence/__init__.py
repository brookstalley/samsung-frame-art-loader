"""Storage for the catalogue, reached only through the service layer.

`catalogue.py` and `discovery.py` name the two contracts, `records.py` and
`discovery_records.py` the records behind them, and `sqlite.py` and
`sqlite_discovery.py` the adapters that implement them over one open file.
Nothing above this package imports a backend directly, which is what keeps
replacing one a change confined to it.
"""
