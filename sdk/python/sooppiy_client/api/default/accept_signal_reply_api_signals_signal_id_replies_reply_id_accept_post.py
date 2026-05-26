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
    signal_id: int,
    reply_id: int,
    *,
    authorization: str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(authorization, Unset):
        headers["authorization"] = authorization



    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/signals/{signal_id}/replies/{reply_id}/accept".format(signal_id=quote(str(signal_id), safe=""),reply_id=quote(str(reply_id), safe=""),),
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
    signal_id: int,
    reply_id: int,
    *,
    client: AuthenticatedClient | Client,
    authorization: str | Unset = UNSET,

) -> Response[Any | HTTPValidationError]:
    """ Accept Signal Reply

    Args:
        signal_id (int):
        reply_id (int):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        signal_id=signal_id,
reply_id=reply_id,
authorization=authorization,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    signal_id: int,
    reply_id: int,
    *,
    client: AuthenticatedClient | Client,
    authorization: str | Unset = UNSET,

) -> Any | HTTPValidationError | None:
    """ Accept Signal Reply

    Args:
        signal_id (int):
        reply_id (int):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        signal_id=signal_id,
reply_id=reply_id,
client=client,
authorization=authorization,

    ).parsed

async def asyncio_detailed(
    signal_id: int,
    reply_id: int,
    *,
    client: AuthenticatedClient | Client,
    authorization: str | Unset = UNSET,

) -> Response[Any | HTTPValidationError]:
    """ Accept Signal Reply

    Args:
        signal_id (int):
        reply_id (int):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        signal_id=signal_id,
reply_id=reply_id,
authorization=authorization,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    signal_id: int,
    reply_id: int,
    *,
    client: AuthenticatedClient | Client,
    authorization: str | Unset = UNSET,

) -> Any | HTTPValidationError | None:
    """ Accept Signal Reply

    Args:
        signal_id (int):
        reply_id (int):
        authorization (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        signal_id=signal_id,
reply_id=reply_id,
client=client,
authorization=authorization,

    )).parsed
