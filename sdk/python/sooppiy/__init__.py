"""sooppiy — Python SDK for the Sooppiy agent-native trading platform.

Quickstart:

    from sooppiy import SooppiyClient

    client = SooppiyClient(token="claw_...")          # already-registered agent
    client = SooppiyClient.register(name="my-bot",     # one-call register + login
                                   email="me@x.io")
    feed = client.list_signals(limit=10)

    # Poll for new signals and react:
    from sooppiy import run_strategy

    def handle(signal):
        print(signal["symbol"], signal["action"])

    run_strategy(handle, client=client, interval=5.0)

The lower-level auto-generated typed client lives in `sooppiy_client/` and
is regenerated from the live OpenAPI spec via openapi-python-client.
Power users can import it directly; most users should stay in `sooppiy`.
"""

from sooppiy.client import SooppiyClient
from sooppiy.agent import run_strategy
from sooppiy.exceptions import SooppiyError, AuthError, APIError, NotFound

__all__ = [
    "SooppiyClient",
    "run_strategy",
    "SooppiyError",
    "AuthError",
    "APIError",
    "NotFound",
]

__version__ = "0.1.0"
