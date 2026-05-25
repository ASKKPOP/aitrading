from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    agent_id: int,
    start_at: str,
    end_at: str,
    initial_cash: float | Unset = 100000.0,
    market: None | str | Unset = UNSET,
    symbol: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["agent_id"] = agent_id

    params["start_at"] = start_at

    params["end_at"] = end_at

    params["initial_cash"] = initial_cash

    json_market: None | str | Unset
    if isinstance(market, Unset):
        json_market = UNSET
    else:
        json_market = market
    params["market"] = json_market

    json_symbol: None | str | Unset
    if isinstance(symbol, Unset):
        json_symbol = UNSET
    else:
        json_symbol = symbol
    params["symbol"] = json_symbol


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/research/backtest",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent_id: int,
    start_at: str,
    end_at: str,
    initial_cash: float | Unset = 100000.0,
    market: None | str | Unset = UNSET,
    symbol: None | str | Unset = UNSET,

) -> Response[Any | HTTPValidationError]:
    """ Api Backtest

     Replay an agent's recorded trades and return P&L metrics.

    Query parameters:
      agent_id      – required; agent whose signals to replay
      start_at      – required; ISO-8601 UTC window start (e.g. 2024-01-01T00:00:00Z)
      end_at        – required; ISO-8601 UTC window end
      initial_cash  – starting balance (default 100 000)
      market        – optional filter (e.g. us-stock)
      symbol        – optional filter (e.g. AAPL)

    Args:
        agent_id (int):
        start_at (str):
        end_at (str):
        initial_cash (float | Unset):  Default: 100000.0.
        market (None | str | Unset):
        symbol (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        agent_id=agent_id,
start_at=start_at,
end_at=end_at,
initial_cash=initial_cash,
market=market,
symbol=symbol,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient | Client,
    agent_id: int,
    start_at: str,
    end_at: str,
    initial_cash: float | Unset = 100000.0,
    market: None | str | Unset = UNSET,
    symbol: None | str | Unset = UNSET,

) -> Any | HTTPValidationError | None:
    """ Api Backtest

     Replay an agent's recorded trades and return P&L metrics.

    Query parameters:
      agent_id      – required; agent whose signals to replay
      start_at      – required; ISO-8601 UTC window start (e.g. 2024-01-01T00:00:00Z)
      end_at        – required; ISO-8601 UTC window end
      initial_cash  – starting balance (default 100 000)
      market        – optional filter (e.g. us-stock)
      symbol        – optional filter (e.g. AAPL)

    Args:
        agent_id (int):
        start_at (str):
        end_at (str):
        initial_cash (float | Unset):  Default: 100000.0.
        market (None | str | Unset):
        symbol (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        client=client,
agent_id=agent_id,
start_at=start_at,
end_at=end_at,
initial_cash=initial_cash,
market=market,
symbol=symbol,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent_id: int,
    start_at: str,
    end_at: str,
    initial_cash: float | Unset = 100000.0,
    market: None | str | Unset = UNSET,
    symbol: None | str | Unset = UNSET,

) -> Response[Any | HTTPValidationError]:
    """ Api Backtest

     Replay an agent's recorded trades and return P&L metrics.

    Query parameters:
      agent_id      – required; agent whose signals to replay
      start_at      – required; ISO-8601 UTC window start (e.g. 2024-01-01T00:00:00Z)
      end_at        – required; ISO-8601 UTC window end
      initial_cash  – starting balance (default 100 000)
      market        – optional filter (e.g. us-stock)
      symbol        – optional filter (e.g. AAPL)

    Args:
        agent_id (int):
        start_at (str):
        end_at (str):
        initial_cash (float | Unset):  Default: 100000.0.
        market (None | str | Unset):
        symbol (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        agent_id=agent_id,
start_at=start_at,
end_at=end_at,
initial_cash=initial_cash,
market=market,
symbol=symbol,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    agent_id: int,
    start_at: str,
    end_at: str,
    initial_cash: float | Unset = 100000.0,
    market: None | str | Unset = UNSET,
    symbol: None | str | Unset = UNSET,

) -> Any | HTTPValidationError | None:
    """ Api Backtest

     Replay an agent's recorded trades and return P&L metrics.

    Query parameters:
      agent_id      – required; agent whose signals to replay
      start_at      – required; ISO-8601 UTC window start (e.g. 2024-01-01T00:00:00Z)
      end_at        – required; ISO-8601 UTC window end
      initial_cash  – starting balance (default 100 000)
      market        – optional filter (e.g. us-stock)
      symbol        – optional filter (e.g. AAPL)

    Args:
        agent_id (int):
        start_at (str):
        end_at (str):
        initial_cash (float | Unset):  Default: 100000.0.
        market (None | str | Unset):
        symbol (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
agent_id=agent_id,
start_at=start_at,
end_at=end_at,
initial_cash=initial_cash,
market=market,
symbol=symbol,

    )).parsed
