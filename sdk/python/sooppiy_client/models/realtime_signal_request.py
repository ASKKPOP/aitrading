from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RealtimeSignalRequest")



@_attrs_define
class RealtimeSignalRequest:
    """ 
        Attributes:
            market (str):
            action (str):
            symbol (str):
            price (float):
            quantity (float):
            executed_at (str):
            content (None | str | Unset):
            token_id (None | str | Unset):
            outcome (None | str | Unset):
     """

    market: str
    action: str
    symbol: str
    price: float
    quantity: float
    executed_at: str
    content: None | str | Unset = UNSET
    token_id: None | str | Unset = UNSET
    outcome: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        market = self.market

        action = self.action

        symbol = self.symbol

        price = self.price

        quantity = self.quantity

        executed_at = self.executed_at

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        token_id: None | str | Unset
        if isinstance(self.token_id, Unset):
            token_id = UNSET
        else:
            token_id = self.token_id

        outcome: None | str | Unset
        if isinstance(self.outcome, Unset):
            outcome = UNSET
        else:
            outcome = self.outcome


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "market": market,
            "action": action,
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "executed_at": executed_at,
        })
        if content is not UNSET:
            field_dict["content"] = content
        if token_id is not UNSET:
            field_dict["token_id"] = token_id
        if outcome is not UNSET:
            field_dict["outcome"] = outcome

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        market = d.pop("market")

        action = d.pop("action")

        symbol = d.pop("symbol")

        price = d.pop("price")

        quantity = d.pop("quantity")

        executed_at = d.pop("executed_at")

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))


        def _parse_token_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        token_id = _parse_token_id(d.pop("token_id", UNSET))


        def _parse_outcome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        outcome = _parse_outcome(d.pop("outcome", UNSET))


        realtime_signal_request = cls(
            market=market,
            action=action,
            symbol=symbol,
            price=price,
            quantity=quantity,
            executed_at=executed_at,
            content=content,
            token_id=token_id,
            outcome=outcome,
        )


        realtime_signal_request.additional_properties = d
        return realtime_signal_request

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
