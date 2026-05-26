from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.agent_task_create_input_data_type_0 import AgentTaskCreateInputDataType0





T = TypeVar("T", bound="AgentTaskCreate")



@_attrs_define
class AgentTaskCreate:
    """ 
        Attributes:
            agent_id (int):
            type_ (str):
            input_data (AgentTaskCreateInputDataType0 | None | Unset):
     """

    agent_id: int
    type_: str
    input_data: AgentTaskCreateInputDataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_task_create_input_data_type_0 import AgentTaskCreateInputDataType0
        agent_id = self.agent_id

        type_ = self.type_

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, AgentTaskCreateInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "agent_id": agent_id,
            "type": type_,
        })
        if input_data is not UNSET:
            field_dict["input_data"] = input_data

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_task_create_input_data_type_0 import AgentTaskCreateInputDataType0
        d = dict(src_dict)
        agent_id = d.pop("agent_id")

        type_ = d.pop("type")

        def _parse_input_data(data: object) -> AgentTaskCreateInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = AgentTaskCreateInputDataType0.from_dict(data)



                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentTaskCreateInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))


        agent_task_create = cls(
            agent_id=agent_id,
            type_=type_,
            input_data=input_data,
        )


        agent_task_create.additional_properties = d
        return agent_task_create

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
