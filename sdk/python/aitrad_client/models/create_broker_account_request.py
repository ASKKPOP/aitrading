from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="CreateBrokerAccountRequest")



@_attrs_define
class CreateBrokerAccountRequest:
    """ 
        Attributes:
            broker (str):
            api_key (str):
            api_secret (str):
     """

    broker: str
    api_key: str
    api_secret: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        broker = self.broker

        api_key = self.api_key

        api_secret = self.api_secret


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "broker": broker,
            "api_key": api_key,
            "api_secret": api_secret,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        broker = d.pop("broker")

        api_key = d.pop("api_key")

        api_secret = d.pop("api_secret")

        create_broker_account_request = cls(
            broker=broker,
            api_key=api_key,
            api_secret=api_secret,
        )


        create_broker_account_request.additional_properties = d
        return create_broker_account_request

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
