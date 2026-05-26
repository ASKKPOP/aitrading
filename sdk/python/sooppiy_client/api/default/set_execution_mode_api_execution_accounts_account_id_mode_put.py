from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.set_execution_mode_request import SetExecutionModeRequest
from typing import cast



def _get_kwargs(
    account_id: int,
    *,
    body: SetExecutionModeRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/execution/accounts/{account_id}/mode".format(account_id=quote(str(account_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

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
    account_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: SetExecutionModeRequest,

) -> Response[Any | HTTPValidationError]:
    """ Set Execution Mode

    Args:
        account_id (int):
        body (SetExecutionModeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        account_id=account_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    account_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: SetExecutionModeRequest,

) -> Any | HTTPValidationError | None:
    """ Set Execution Mode

    Args:
        account_id (int):
        body (SetExecutionModeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        account_id=account_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    account_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: SetExecutionModeRequest,

) -> Response[Any | HTTPValidationError]:
    """ Set Execution Mode

    Args:
        account_id (int):
        body (SetExecutionModeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        account_id=account_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    account_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: SetExecutionModeRequest,

) -> Any | HTTPValidationError | None:
    """ Set Execution Mode

    Args:
        account_id (int):
        body (SetExecutionModeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        account_id=account_id,
client=client,
body=body,

    )).parsed
