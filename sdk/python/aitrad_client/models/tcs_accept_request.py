from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="TcsAcceptRequest")



@_attrs_define
class TcsAcceptRequest:
    """ 
        Attributes:
            broker (str):
            tcs_version (str | Unset):  Default: 'v1'.
     """

    broker: str
    tcs_version: str | Unset = 'v1'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        broker = self.broker

        tcs_version = self.tcs_version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "broker": broker,
        })
        if tcs_version is not UNSET:
            field_dict["tcs_version"] = tcs_version

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        broker = d.pop("broker")

        tcs_version = d.pop("tcs_version", UNSET)

        tcs_accept_request = cls(
            broker=broker,
            tcs_version=tcs_version,
        )


        tcs_accept_request.additional_properties = d
        return tcs_accept_request

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
