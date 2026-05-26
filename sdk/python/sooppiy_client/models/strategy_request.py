from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="StrategyRequest")



@_attrs_define
class StrategyRequest:
    """ 
        Attributes:
            market (str):
            title (str):
            content (str):
            symbols (None | str | Unset):
            tags (None | str | Unset):
            challenge_key (None | str | Unset):
            mission_key (None | str | Unset):
            team_key (None | str | Unset):
     """

    market: str
    title: str
    content: str
    symbols: None | str | Unset = UNSET
    tags: None | str | Unset = UNSET
    challenge_key: None | str | Unset = UNSET
    mission_key: None | str | Unset = UNSET
    team_key: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        market = self.market

        title = self.title

        content = self.content

        symbols: None | str | Unset
        if isinstance(self.symbols, Unset):
            symbols = UNSET
        else:
            symbols = self.symbols

        tags: None | str | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        else:
            tags = self.tags

        challenge_key: None | str | Unset
        if isinstance(self.challenge_key, Unset):
            challenge_key = UNSET
        else:
            challenge_key = self.challenge_key

        mission_key: None | str | Unset
        if isinstance(self.mission_key, Unset):
            mission_key = UNSET
        else:
            mission_key = self.mission_key

        team_key: None | str | Unset
        if isinstance(self.team_key, Unset):
            team_key = UNSET
        else:
            team_key = self.team_key


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "market": market,
            "title": title,
            "content": content,
        })
        if symbols is not UNSET:
            field_dict["symbols"] = symbols
        if tags is not UNSET:
            field_dict["tags"] = tags
        if challenge_key is not UNSET:
            field_dict["challenge_key"] = challenge_key
        if mission_key is not UNSET:
            field_dict["mission_key"] = mission_key
        if team_key is not UNSET:
            field_dict["team_key"] = team_key

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        market = d.pop("market")

        title = d.pop("title")

        content = d.pop("content")

        def _parse_symbols(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        symbols = _parse_symbols(d.pop("symbols", UNSET))


        def _parse_tags(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))


        def _parse_challenge_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        challenge_key = _parse_challenge_key(d.pop("challenge_key", UNSET))


        def _parse_mission_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_key = _parse_mission_key(d.pop("mission_key", UNSET))


        def _parse_team_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        team_key = _parse_team_key(d.pop("team_key", UNSET))


        strategy_request = cls(
            market=market,
            title=title,
            content=content,
            symbols=symbols,
            tags=tags,
            challenge_key=challenge_key,
            mission_key=mission_key,
            team_key=team_key,
        )


        strategy_request.additional_properties = d
        return strategy_request

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
