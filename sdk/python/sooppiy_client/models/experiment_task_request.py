from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.experiment_task_request_input_data_type_0 import ExperimentTaskRequestInputDataType0





T = TypeVar("T", bound="ExperimentTaskRequest")



@_attrs_define
class ExperimentTaskRequest:
    """ 
        Attributes:
            task_type (str):
            input_data (ExperimentTaskRequestInputDataType0 | None | Unset):
            experiment_key (None | str | Unset):
            variant_key (None | str | Unset):
            challenge_key (None | str | Unset):
            mission_key (None | str | Unset):
            team_key (None | str | Unset):
            agent_ids (list[int] | None | Unset):
            target (None | str | Unset):
            dry_run (bool | Unset):  Default: True.
            limit (int | Unset):  Default: 500.
     """

    task_type: str
    input_data: ExperimentTaskRequestInputDataType0 | None | Unset = UNSET
    experiment_key: None | str | Unset = UNSET
    variant_key: None | str | Unset = UNSET
    challenge_key: None | str | Unset = UNSET
    mission_key: None | str | Unset = UNSET
    team_key: None | str | Unset = UNSET
    agent_ids: list[int] | None | Unset = UNSET
    target: None | str | Unset = UNSET
    dry_run: bool | Unset = True
    limit: int | Unset = 500
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.experiment_task_request_input_data_type_0 import ExperimentTaskRequestInputDataType0
        task_type = self.task_type

        input_data: dict[str, Any] | None | Unset
        if isinstance(self.input_data, Unset):
            input_data = UNSET
        elif isinstance(self.input_data, ExperimentTaskRequestInputDataType0):
            input_data = self.input_data.to_dict()
        else:
            input_data = self.input_data

        experiment_key: None | str | Unset
        if isinstance(self.experiment_key, Unset):
            experiment_key = UNSET
        else:
            experiment_key = self.experiment_key

        variant_key: None | str | Unset
        if isinstance(self.variant_key, Unset):
            variant_key = UNSET
        else:
            variant_key = self.variant_key

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

        agent_ids: list[int] | None | Unset
        if isinstance(self.agent_ids, Unset):
            agent_ids = UNSET
        elif isinstance(self.agent_ids, list):
            agent_ids = self.agent_ids


        else:
            agent_ids = self.agent_ids

        target: None | str | Unset
        if isinstance(self.target, Unset):
            target = UNSET
        else:
            target = self.target

        dry_run = self.dry_run

        limit = self.limit


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "task_type": task_type,
        })
        if input_data is not UNSET:
            field_dict["input_data"] = input_data
        if experiment_key is not UNSET:
            field_dict["experiment_key"] = experiment_key
        if variant_key is not UNSET:
            field_dict["variant_key"] = variant_key
        if challenge_key is not UNSET:
            field_dict["challenge_key"] = challenge_key
        if mission_key is not UNSET:
            field_dict["mission_key"] = mission_key
        if team_key is not UNSET:
            field_dict["team_key"] = team_key
        if agent_ids is not UNSET:
            field_dict["agent_ids"] = agent_ids
        if target is not UNSET:
            field_dict["target"] = target
        if dry_run is not UNSET:
            field_dict["dry_run"] = dry_run
        if limit is not UNSET:
            field_dict["limit"] = limit

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.experiment_task_request_input_data_type_0 import ExperimentTaskRequestInputDataType0
        d = dict(src_dict)
        task_type = d.pop("task_type")

        def _parse_input_data(data: object) -> ExperimentTaskRequestInputDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_data_type_0 = ExperimentTaskRequestInputDataType0.from_dict(data)



                return input_data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ExperimentTaskRequestInputDataType0 | None | Unset, data)

        input_data = _parse_input_data(d.pop("input_data", UNSET))


        def _parse_experiment_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        experiment_key = _parse_experiment_key(d.pop("experiment_key", UNSET))


        def _parse_variant_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        variant_key = _parse_variant_key(d.pop("variant_key", UNSET))


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


        def _parse_agent_ids(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                agent_ids_type_0 = cast(list[int], data)

                return agent_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        agent_ids = _parse_agent_ids(d.pop("agent_ids", UNSET))


        def _parse_target(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        target = _parse_target(d.pop("target", UNSET))


        dry_run = d.pop("dry_run", UNSET)

        limit = d.pop("limit", UNSET)

        experiment_task_request = cls(
            task_type=task_type,
            input_data=input_data,
            experiment_key=experiment_key,
            variant_key=variant_key,
            challenge_key=challenge_key,
            mission_key=mission_key,
            team_key=team_key,
            agent_ids=agent_ids,
            target=target,
            dry_run=dry_run,
            limit=limit,
        )


        experiment_task_request.additional_properties = d
        return experiment_task_request

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
