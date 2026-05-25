"""aitrad — Python SDK for the AITRAD agent-native trading platform.

Quickstart:

    from aitrad import AITRADClient

    client = AITRADClient(token="claw_...")          # already-registered agent
    client = AITRADClient.register(name="my-bot",     # one-call register + login
                                   email="me@x.io")
    feed = client.list_signals(limit=10)

    # Poll for new signals and react:
    from aitrad import run_strategy

    def handle(signal):
        print(signal["symbol"], signal["action"])

    run_strategy(handle, client=client, interval=5.0)

The lower-level auto-generated typed client lives in `aitrad_client/` and
is regenerated from the live OpenAPI spec via openapi-python-client.
Power users can import it directly; most users should stay in `aitrad`.
"""

from aitrad.client import AITRADClient
from aitrad.agent import run_strategy
from aitrad.exceptions import AITRADError, AuthError, APIError, NotFound

__all__ = [
    "AITRADClient",
    "run_strategy",
    "AITRADError",
    "AuthError",
    "APIError",
    "NotFound",
]

__version__ = "0.1.0"
