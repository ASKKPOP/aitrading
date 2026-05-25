from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ChallengeJoinRequest")



@_attrs_define
class ChallengeJoinRequest:
    """ 
        Attributes:
            variant_key (None | str | Unset):
            starting_cash (float | None | Unset):
     """

    variant_key: None | str | Unset = UNSET
    starting_cash: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        variant_key: None | str | Unset
        if isinstance(self.variant_key, Unset):
            variant_key = UNSET
        else:
            variant_key = self.variant_key

        starting_cash: float | None | Unset
        if isinstance(self.starting_cash, Unset):
            starting_cash = UNSET
        else:
            starting_cash = self.starting_cash


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if variant_key is not UNSET:
            field_dict["variant_key"] = variant_key
        if starting_cash is not UNSET:
            field_dict["starting_cash"] = starting_cash

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_variant_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        variant_key = _parse_variant_key(d.pop("variant_key", UNSET))


        def _parse_starting_cash(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        starting_cash = _parse_starting_cash(d.pop("starting_cash", UNSET))


        challenge_join_request = cls(
            variant_key=variant_key,
            starting_cash=starting_cash,
        )


        challenge_join_request.additional_properties = d
        return challenge_join_request

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
