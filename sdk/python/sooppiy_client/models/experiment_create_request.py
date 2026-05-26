from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.experiment_create_request_variants_json_type_0_item import ExperimentCreateRequestVariantsJsonType0Item





T = TypeVar("T", bound="ExperimentCreateRequest")



@_attrs_define
class ExperimentCreateRequest:
    """ 
        Attributes:
            title (str):
            experiment_key (None | str | Unset):
            description (None | str | Unset):
            status (str | Unset):  Default: 'active'.
            unit_type (str | Unset):  Default: 'agent'.
            variants_json (list[ExperimentCreateRequestVariantsJsonType0Item] | None | Unset):
            start_at (None | str | Unset):
            end_at (None | str | Unset):
     """

    title: str
    experiment_key: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    status: str | Unset = 'active'
    unit_type: str | Unset = 'agent'
    variants_json: list[ExperimentCreateRequestVariantsJsonType0Item] | None | Unset = UNSET
    start_at: None | str | Unset = UNSET
    end_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.experiment_create_request_variants_json_type_0_item import ExperimentCreateRequestVariantsJsonType0Item
        title = self.title

        experiment_key: None | str | Unset
        if isinstance(self.experiment_key, Unset):
            experiment_key = UNSET
        else:
            experiment_key = self.experiment_key

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        status = self.status

        unit_type = self.unit_type

        variants_json: list[dict[str, Any]] | None | Unset
        if isinstance(self.variants_json, Unset):
            variants_json = UNSET
        elif isinstance(self.variants_json, list):
            variants_json = []
            for variants_json_type_0_item_data in self.variants_json:
                variants_json_type_0_item = variants_json_type_0_item_data.to_dict()
                variants_json.append(variants_json_type_0_item)


        else:
            variants_json = self.variants_json

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


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "title": title,
        })
        if experiment_key is not UNSET:
            field_dict["experiment_key"] = experiment_key
        if description is not UNSET:
            field_dict["description"] = description
        if status is not UNSET:
            field_dict["status"] = status
        if unit_type is not UNSET:
            field_dict["unit_type"] = unit_type
        if variants_json is not UNSET:
            field_dict["variants_json"] = variants_json
        if start_at is not UNSET:
            field_dict["start_at"] = start_at
        if end_at is not UNSET:
            field_dict["end_at"] = end_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.experiment_create_request_variants_json_type_0_item import ExperimentCreateRequestVariantsJsonType0Item
        d = dict(src_dict)
        title = d.pop("title")

        def _parse_experiment_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        experiment_key = _parse_experiment_key(d.pop("experiment_key", UNSET))


        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        status = d.pop("status", UNSET)

        unit_type = d.pop("unit_type", UNSET)

        def _parse_variants_json(data: object) -> list[ExperimentCreateRequestVariantsJsonType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                variants_json_type_0 = []
                _variants_json_type_0 = data
                for variants_json_type_0_item_data in (_variants_json_type_0):
                    variants_json_type_0_item = ExperimentCreateRequestVariantsJsonType0Item.from_dict(variants_json_type_0_item_data)



                    variants_json_type_0.append(variants_json_type_0_item)

                return variants_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ExperimentCreateRequestVariantsJsonType0Item] | None | Unset, data)

        variants_json = _parse_variants_json(d.pop("variants_json", UNSET))


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


        experiment_create_request = cls(
            title=title,
            experiment_key=experiment_key,
            description=description,
            status=status,
            unit_type=unit_type,
            variants_json=variants_json,
            start_at=start_at,
            end_at=end_at,
        )


        experiment_create_request.additional_properties = d
        return experiment_create_request

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
