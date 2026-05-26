from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.submit_entry_request import SubmitEntryRequest
from typing import cast



def _get_kwargs(
    tid: int,
    *,
    body: SubmitEntryRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/tournaments/{tid}/entries".format(tid=quote(str(tid), safe=""),),
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = response.json()
        return response_201

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
    tid: int,
    *,
    client: AuthenticatedClient | Client,
    body: SubmitEntryRequest,

) -> Response[Any | HTTPValidationError]:
    """ Submit Entry

    Args:
        tid (int):
        body (SubmitEntryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        tid=tid,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    tid: int,
    *,
    client: AuthenticatedClient | Client,
    body: SubmitEntryRequest,

) -> Any | HTTPValidationError | None:
    """ Submit Entry

    Args:
        tid (int):
        body (SubmitEntryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        tid=tid,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    tid: int,
    *,
    client: AuthenticatedClient | Client,
    body: SubmitEntryRequest,

) -> Response[Any | HTTPValidationError]:
    """ Submit Entry

    Args:
        tid (int):
        body (SubmitEntryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        tid=tid,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    tid: int,
    *,
    client: AuthenticatedClient | Client,
    body: SubmitEntryRequest,

) -> Any | HTTPValidationError | None:
    """ Submit Entry

    Args:
        tid (int):
        body (SubmitEntryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        tid=tid,
client=client,
body=body,

    )).parsed
