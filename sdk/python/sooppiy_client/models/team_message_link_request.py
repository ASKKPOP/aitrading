from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.team_message_link_request_metadata_json_type_0 import TeamMessageLinkRequestMetadataJsonType0





T = TypeVar("T", bound="TeamMessageLinkRequest")



@_attrs_define
class TeamMessageLinkRequest:
    """ 
        Attributes:
            signal_id (int):
            message_type (str | Unset):  Default: 'signal'.
            content (None | str | Unset):
            metadata_json (None | TeamMessageLinkRequestMetadataJsonType0 | Unset):
     """

    signal_id: int
    message_type: str | Unset = 'signal'
    content: None | str | Unset = UNSET
    metadata_json: None | TeamMessageLinkRequestMetadataJsonType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.team_message_link_request_metadata_json_type_0 import TeamMessageLinkRequestMetadataJsonType0
        signal_id = self.signal_id

        message_type = self.message_type

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        metadata_json: dict[str, Any] | None | Unset
        if isinstance(self.metadata_json, Unset):
            metadata_json = UNSET
        elif isinstance(self.metadata_json, TeamMessageLinkRequestMetadataJsonType0):
            metadata_json = self.metadata_json.to_dict()
        else:
            metadata_json = self.metadata_json


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "signal_id": signal_id,
        })
        if message_type is not UNSET:
            field_dict["message_type"] = message_type
        if content is not UNSET:
            field_dict["content"] = content
        if metadata_json is not UNSET:
            field_dict["metadata_json"] = metadata_json

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.team_message_link_request_metadata_json_type_0 import TeamMessageLinkRequestMetadataJsonType0
        d = dict(src_dict)
        signal_id = d.pop("signal_id")

        message_type = d.pop("message_type", UNSET)

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))


        def _parse_metadata_json(data: object) -> None | TeamMessageLinkRequestMetadataJsonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_json_type_0 = TeamMessageLinkRequestMetadataJsonType0.from_dict(data)



                return metadata_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TeamMessageLinkRequestMetadataJsonType0 | Unset, data)

        metadata_json = _parse_metadata_json(d.pop("metadata_json", UNSET))


        team_message_link_request = cls(
            signal_id=signal_id,
            message_type=message_type,
            content=content,
            metadata_json=metadata_json,
        )


        team_message_link_request.additional_properties = d
        return team_message_link_request

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
