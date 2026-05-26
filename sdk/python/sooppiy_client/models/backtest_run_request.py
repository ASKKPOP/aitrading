from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="BacktestRunRequest")



@_attrs_define
class BacktestRunRequest:
    """ 
        Attributes:
            start_at (str):
            end_at (str):
            initial_cash (float | Unset):  Default: 100000.0.
            market (None | str | Unset):
            symbol (None | str | Unset):
            strategy_id (int | None | Unset):
     """

    start_at: str
    end_at: str
    initial_cash: float | Unset = 100000.0
    market: None | str | Unset = UNSET
    symbol: None | str | Unset = UNSET
    strategy_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        start_at = self.start_at

        end_at = self.end_at

        initial_cash = self.initial_cash

        market: None | str | Unset
        if isinstance(self.market, Unset):
            market = UNSET
        else:
            market = self.market

        symbol: None | str | Unset
        if isinstance(self.symbol, Unset):
            symbol = UNSET
        else:
            symbol = self.symbol

        strategy_id: int | None | Unset
        if isinstance(self.strategy_id, Unset):
            strategy_id = UNSET
        else:
            strategy_id = self.strategy_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "start_at": start_at,
            "end_at": end_at,
        })
        if initial_cash is not UNSET:
            field_dict["initial_cash"] = initial_cash
        if market is not UNSET:
            field_dict["market"] = market
        if symbol is not UNSET:
            field_dict["symbol"] = symbol
        if strategy_id is not UNSET:
            field_dict["strategy_id"] = strategy_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        start_at = d.pop("start_at")

        end_at = d.pop("end_at")

        initial_cash = d.pop("initial_cash", UNSET)

        def _parse_market(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        market = _parse_market(d.pop("market", UNSET))


        def _parse_symbol(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        symbol = _parse_symbol(d.pop("symbol", UNSET))


        def _parse_strategy_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        strategy_id = _parse_strategy_id(d.pop("strategy_id", UNSET))


        backtest_run_request = cls(
            start_at=start_at,
            end_at=end_at,
            initial_cash=initial_cash,
            market=market,
            symbol=symbol,
            strategy_id=strategy_id,
        )


        backtest_run_request.additional_properties = d
        return backtest_run_request

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
