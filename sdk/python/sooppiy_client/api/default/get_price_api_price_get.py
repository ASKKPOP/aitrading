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
    symbol: str,
    market: str | Unset = 'us-stock',
    token_id: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,
    authorization: str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(authorization, Unset):
        headers["authorization"] = authorization



    

    params: dict[str, Any] = {}

    params["symbol"] = symbol

    params["market"] = market

    json_token_id: None | str | Unset
    if isinstance(token_id, Unset):
        json_token_id = UNSET
    else:
        json_token_id = token_id
    params["token_id"] = json_token_id

    json_outcome: None | str | Unset
    if isinstance(outcome, Unset):
        json_outcome = UNSET
    else:
        json_outcome = outcome
    params["outcome"] = json_outcome


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/price",
        "params": params,
    }


    _kwargs["headers"] = headers
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
    symbol: str,
    market: str | Unset = 'us-stock',
    token_id: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,
    authorization: str | Unset = UNSET,

) -> Response[Any | HTTPValidationError]:
    """ Get Price

    Args:
        symbol (str):
        market (str | Unset):  Default: 'us-stock'.
        token_id (None | str | Unset):
        outcome (None | str | Unset):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        symbol=symbol,
market=market,
token_id=token_id,
outcome=outcome,
authorization=authorization,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient | Client,
    symbol: str,
    market: str | Unset = 'us-stock',
    token_id: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,
    authorization: str | Unset = UNSET,

) -> Any | HTTPValidationError | None:
    """ Get Price

    Args:
        symbol (str):
        market (str | Unset):  Default: 'us-stock'.
        token_id (None | str | Unset):
        outcome (None | str | Unset):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        client=client,
symbol=symbol,
market=market,
token_id=token_id,
outcome=outcome,
authorization=authorization,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    symbol: str,
    market: str | Unset = 'us-stock',
    token_id: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,
    authorization: str | Unset = UNSET,

) -> Response[Any | HTTPValidationError]:
    """ Get Price

    Args:
        symbol (str):
        market (str | Unset):  Default: 'us-stock'.
        token_id (None | str | Unset):
        outcome (None | str | Unset):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        symbol=symbol,
market=market,
token_id=token_id,
outcome=outcome,
authorization=authorization,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    symbol: str,
    market: str | Unset = 'us-stock',
    token_id: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,
    authorization: str | Unset = UNSET,

) -> Any | HTTPValidationError | None:
    """ Get Price

    Args:
        symbol (str):
        market (str | Unset):  Default: 'us-stock'.
        token_id (None | str | Unset):
        outcome (None | str | Unset):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
symbol=symbol,
market=market,
token_id=token_id,
outcome=outcome,
authorization=authorization,

    )).parsed
