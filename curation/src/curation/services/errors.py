"""The one exception type the surfaces above the service layer have to know.

Both the MCP bindings and the HTTP handlers translate this into their own
error shape. Keeping it a single type means neither surface grows a per-error
translation table — the thing that turns a thin binding into a thick one.
"""


class ServiceError(Exception):
    """An operation the service refused, carrying a message fit to return.

    The message is written for whoever asked: it names the value that was
    wrong and, where there is one, the thing to do instead. It never carries a
    stack trace or an internal identifier — those go to the log.
    """
