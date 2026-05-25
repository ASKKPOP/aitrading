from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.challenge_create_request_rules_json_type_0 import ChallengeCreateRequestRulesJsonType0





T = TypeVar("T", bound="ChallengeCreateRequest")



@_attrs_define
class ChallengeCreateRequest:
    """ 
        Attributes:
            title (str):
            market (str):
            challenge_key (None | str | Unset):
            description (None | str | Unset):
            symbol (None | str | Unset):
            challenge_type (str | Unset):  Default: 'multi-agent'.
            status (None | str | Unset):
            scoring_method (str | Unset):  Default: 'return-only'.
            initial_capital (float | Unset):  Default: 100000.0.
            max_position_pct (float | Unset):  Default: 100.0.
            max_drawdown_pct (float | Unset):  Default: 100.0.
            start_at (None | str | Unset):
            end_at (None | str | Unset):
            rules_json (ChallengeCreateRequestRulesJsonType0 | None | Unset):
            experiment_key (None | str | Unset):
     """

    title: str
    market: str
    challenge_key: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    symbol: None | str | Unset = UNSET
    challenge_type: str | Unset = 'multi-agent'
    status: None | str | Unset = UNSET
    scoring_method: str | Unset = 'return-only'
    initial_capital: float | Unset = 100000.0
    max_position_pct: float | Unset = 100.0
    max_drawdown_pct: float | Unset = 100.0
    start_at: None | str | Unset = UNSET
    end_at: None | str | Unset = UNSET
    rules_json: ChallengeCreateRequestRulesJsonType0 | None | Unset = UNSET
    experiment_key: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.challenge_create_request_rules_json_type_0 import ChallengeCreateRequestRulesJsonType0
        title = self.title

        market = self.market

        challenge_key: None | str | Unset
        if isinstance(self.challenge_key, Unset):
            challenge_key = UNSET
        else:
            challenge_key = self.challenge_key

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

        challenge_type = self.challenge_type

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        scoring_method = self.scoring_method

        initial_capital = self.initial_capital

        max_position_pct = self.max_position_pct

        max_drawdown_pct = self.max_drawdown_pct

        start_at: None | str | Unset
        if isinstance(self.start_at, Unset):
            start_at = UNSET
        else:
            start_at = self.start_at

        end_at: None | str | Unset
        if isinstance(self.end_at, Unset):
            end_at = UNSET
        else:
            end_at = self.end_at

        rules_json: dict[str, Any] | None | Unset
        if isinstance(self.rules_json, Unset):
            rules_json = UNSET
        elif isinstance(self.rules_json, ChallengeCreateRequestRulesJsonType0):
            rules_json = self.rules_json.to_dict()
        else:
            rules_json = self.rules_json

        experiment_key: None | str | Unset
        if isinstance(self.experiment_key, Unset):
            experiment_key = UNSET
        else:
            experiment_key = self.experiment_key


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "title": title,
            "market": market,
        })
        if challenge_key is not UNSET:
            field_dict["challenge_key"] = challenge_key
        if description is not UNSET:
            field_dict["description"] = description
        if symbol is not UNSET:
            field_dict["symbol"] = symbol
        if challenge_type is not UNSET:
            field_dict["challenge_type"] = challenge_type
        if status is not UNSET:
            field_dict["status"] = status
        if scoring_method is not UNSET:
            field_dict["scoring_method"] = scoring_method
        if initial_capital is not UNSET:
            field_dict["initial_capital"] = initial_capital
        if max_position_pct is not UNSET:
            field_dict["max_position_pct"] = max_position_pct
        if max_drawdown_pct is not UNSET:
            field_dict["max_drawdown_pct"] = max_drawdown_pct
        if start_at is not UNSET:
            field_dict["start_at"] = start_at
        if end_at is not UNSET:
            field_dict["end_at"] = end_at
        if rules_json is not UNSET:
            field_dict["rules_json"] = rules_json
        if experiment_key is not UNSET:
            field_dict["experiment_key"] = experiment_key

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.challenge_create_request_rules_json_type_0 import ChallengeCreateRequestRulesJsonType0
        d = dict(src_dict)
        title = d.pop("title")

        market = d.pop("market")

        def _parse_challenge_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        challenge_key = _parse_challenge_key(d.pop("challenge_key", UNSET))


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


        challenge_type = d.pop("challenge_type", UNSET)

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))


        scoring_method = d.pop("scoring_method", UNSET)

        initial_capital = d.pop("initial_capital", UNSET)

        max_position_pct = d.pop("max_position_pct", UNSET)

        max_drawdown_pct = d.pop("max_drawdown_pct", UNSET)

        def _parse_start_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        start_at = _parse_start_at(d.pop("start_at", UNSET))


        def _parse_end_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        end_at = _parse_end_at(d.pop("end_at", UNSET))


        def _parse_rules_json(data: object) -> ChallengeCreateRequestRulesJsonType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rules_json_type_0 = ChallengeCreateRequestRulesJsonType0.from_dict(data)



                return rules_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChallengeCreateRequestRulesJsonType0 | None | Unset, data)

        rules_json = _parse_rules_json(d.pop("rules_json", UNSET))


        def _parse_experiment_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        experiment_key = _parse_experiment_key(d.pop("experiment_key", UNSET))


        challenge_create_request = cls(
            title=title,
            market=market,
            challenge_key=challenge_key,
            description=description,
            symbol=symbol,
            challenge_type=challenge_type,
            status=status,
            scoring_method=scoring_method,
            initial_capital=initial_capital,
            max_position_pct=max_position_pct,
            max_drawdown_pct=max_drawdown_pct,
            start_at=start_at,
            end_at=end_at,
            rules_json=rules_json,
            experiment_key=experiment_key,
        )


        challenge_create_request.additional_properties = d
        return challenge_create_request

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
