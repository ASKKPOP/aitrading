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
    start_at: None | str | Unset = UNSET,
    end_at: None | str | Unset = UNSET,
    experiment_key: None | str | Unset = UNSET,
    variant_key: None | str | Unset = UNSET,
    market: None | str | Unset = UNSET,
    agent_ids: None | str | Unset = UNSET,
    anonymize: bool | Unset = True,
    include_content: bool | Unset = True,
    limit: int | Unset = 1000,
    offset: int | Unset = 0,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_start_at: None | str | Unset
    if isinstance(start_at, Unset):
        json_start_at = UNSET
    else:
        json_start_at = start_at
    params["start_at"] = json_start_at

    json_end_at: None | str | Unset
    if isinstance(end_at, Unset):
        json_end_at = UNSET
    else:
        json_end_at = end_at
    params["end_at"] = json_end_at

    json_experiment_key: None | str | Unset
    if isinstance(experiment_key, Unset):
        json_experiment_key = UNSET
    else:
        json_experiment_key = experiment_key
    params["experiment_key"] = json_experiment_key

    json_variant_key: None | str | Unset
    if isinstance(variant_key, Unset):
        json_variant_key = UNSET
    else:
        json_variant_key = variant_key
    params["variant_key"] = json_variant_key

    json_market: None | str | Unset
    if isinstance(market, Unset):
        json_market = UNSET
    else:
        json_market = market
    params["market"] = json_market

    json_agent_ids: None | str | Unset
    if isinstance(agent_ids, Unset):
        json_agent_ids = UNSET
    else:
        json_agent_ids = agent_ids
    params["agent_ids"] = json_agent_ids

    params["anonymize"] = anonymize

    params["include_content"] = include_content

    params["limit"] = limit

    params["offset"] = offset


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/research/events",
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
    start_at: None | str | Unset = UNSET,
    end_at: None | str | Unset = UNSET,
    experiment_key: None | str | Unset = UNSET,
    variant_key: None | str | Unset = UNSET,
    market: None | str | Unset = UNSET,
    agent_ids: None | str | Unset = UNSET,
    anonymize: bool | Unset = True,
    include_content: bool | Unset = True,
    limit: int | Unset = 1000,
    offset: int | Unset = 0,

) -> Response[Any | HTTPValidationError]:
    """ Api Research Events

    Args:
        start_at (None | str | Unset):
        end_at (None | str | Unset):
        experiment_key (None | str | Unset):
        variant_key (None | str | Unset):
        market (None | str | Unset):
        agent_ids (None | str | Unset):
        anonymize (bool | Unset):  Default: True.
        include_content (bool | Unset):  Default: True.
        limit (int | Unset):  Default: 1000.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        start_at=start_at,
end_at=end_at,
experiment_key=experiment_key,
variant_key=variant_key,
market=market,
agent_ids=agent_ids,
anonymize=anonymize,
include_content=include_content,
limit=limit,
offset=offset,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient | Client,
    start_at: None | str | Unset = UNSET,
    end_at: None | str | Unset = UNSET,
    experiment_key: None | str | Unset = UNSET,
    variant_key: None | str | Unset = UNSET,
    market: None | str | Unset = UNSET,
    agent_ids: None | str | Unset = UNSET,
    anonymize: bool | Unset = True,
    include_content: bool | Unset = True,
    limit: int | Unset = 1000,
    offset: int | Unset = 0,

) -> Any | HTTPValidationError | None:
    """ Api Research Events

    Args:
        start_at (None | str | Unset):
        end_at (None | str | Unset):
        experiment_key (None | str | Unset):
        variant_key (None | str | Unset):
        market (None | str | Unset):
        agent_ids (None | str | Unset):
        anonymize (bool | Unset):  Default: True.
        include_content (bool | Unset):  Default: True.
        limit (int | Unset):  Default: 1000.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        client=client,
start_at=start_at,
end_at=end_at,
experiment_key=experiment_key,
variant_key=variant_key,
market=market,
agent_ids=agent_ids,
anonymize=anonymize,
include_content=include_content,
limit=limit,
offset=offset,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    start_at: None | str | Unset = UNSET,
    end_at: None | str | Unset = UNSET,
    experiment_key: None | str | Unset = UNSET,
    variant_key: None | str | Unset = UNSET,
    market: None | str | Unset = UNSET,
    agent_ids: None | str | Unset = UNSET,
    anonymize: bool | Unset = True,
    include_content: bool | Unset = True,
    limit: int | Unset = 1000,
    offset: int | Unset = 0,

) -> Response[Any | HTTPValidationError]:
    """ Api Research Events

    Args:
        start_at (None | str | Unset):
        end_at (None | str | Unset):
        experiment_key (None | str | Unset):
        variant_key (None | str | Unset):
        market (None | str | Unset):
        agent_ids (None | str | Unset):
        anonymize (bool | Unset):  Default: True.
        include_content (bool | Unset):  Default: True.
        limit (int | Unset):  Default: 1000.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        start_at=start_at,
end_at=end_at,
experiment_key=experiment_key,
variant_key=variant_key,
market=market,
agent_ids=agent_ids,
anonymize=anonymize,
include_content=include_content,
limit=limit,
offset=offset,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    start_at: None | str | Unset = UNSET,
    end_at: None | str | Unset = UNSET,
    experiment_key: None | str | Unset = UNSET,
    variant_key: None | str | Unset = UNSET,
    market: None | str | Unset = UNSET,
    agent_ids: None | str | Unset = UNSET,
    anonymize: bool | Unset = True,
    include_content: bool | Unset = True,
    limit: int | Unset = 1000,
    offset: int | Unset = 0,

) -> Any | HTTPValidationError | None:
    """ Api Research Events

    Args:
        start_at (None | str | Unset):
        end_at (None | str | Unset):
        experiment_key (None | str | Unset):
        variant_key (None | str | Unset):
        market (None | str | Unset):
        agent_ids (None | str | Unset):
        anonymize (bool | Unset):  Default: True.
        include_content (bool | Unset):  Default: True.
        limit (int | Unset):  Default: 1000.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
start_at=start_at,
end_at=end_at,
experiment_key=experiment_key,
variant_key=variant_key,
market=market,
agent_ids=agent_ids,
anonymize=anonymize,
include_content=include_content,
limit=limit,
offset=offset,

    )).parsed
