from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="CreateTournamentRequest")



@_attrs_define
class CreateTournamentRequest:
    """ 
        Attributes:
            name (str):
            submission_deadline (str):
            evaluation_start (str):
            evaluation_end (str):
            description (None | str | Unset):
            symbol (None | str | Unset):
            market (str | Unset):  Default: 'us-stock'.
            initial_cash (float | Unset):  Default: 100000.0.
     """

    name: str
    submission_deadline: str
    evaluation_start: str
    evaluation_end: str
    description: None | str | Unset = UNSET
    symbol: None | str | Unset = UNSET
    market: str | Unset = 'us-stock'
    initial_cash: float | Unset = 100000.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        name = self.name

        submission_deadline = self.submission_deadline

        evaluation_start = self.evaluation_start

        evaluation_end = self.evaluation_end

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        symbol: None | str | Unset
        if isinstance(self.symbol, Unset):
            symbol = UNSET
        else:
            symbol = self.symbol

        market = self.market

        initial_cash = self.initial_cash


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
            "submission_deadline": submission_deadline,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if symbol is not UNSET:
            field_dict["symbol"] = symbol
        if market is not UNSET:
            field_dict["market"] = market
        if initial_cash is not UNSET:
            field_dict["initial_cash"] = initial_cash

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        submission_deadline = d.pop("submission_deadline")

        evaluation_start = d.pop("evaluation_start")

        evaluation_end = d.pop("evaluation_end")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        def _parse_symbol(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        symbol = _parse_symbol(d.pop("symbol", UNSET))


        market = d.pop("market", UNSET)

        initial_cash = d.pop("initial_cash", UNSET)

        create_tournament_request = cls(
            name=name,
            submission_deadline=submission_deadline,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            description=description,
            symbol=symbol,
            market=market,
            initial_cash=initial_cash,
        )


        create_tournament_request.additional_properties = d
        return create_tournament_request

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
