from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.team_mission_create_request_rules_json_type_0 import TeamMissionCreateRequestRulesJsonType0





T = TypeVar("T", bound="TeamMissionCreateRequest")



@_attrs_define
class TeamMissionCreateRequest:
    """ 
        Attributes:
            title (str):
            market (str):
            mission_key (None | str | Unset):
            description (None | str | Unset):
            symbol (None | str | Unset):
            mission_type (str | Unset):  Default: 'consensus'.
            status (None | str | Unset):
            team_size_min (int | Unset):  Default: 2.
            team_size_max (int | Unset):  Default: 5.
            assignment_mode (str | Unset):  Default: 'random'.
            required_roles_json (list[str] | None | Unset):
            start_at (None | str | Unset):
            submission_due_at (None | str | Unset):
            rules_json (None | TeamMissionCreateRequestRulesJsonType0 | Unset):
            experiment_key (None | str | Unset):
     """

    title: str
    market: str
    mission_key: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    symbol: None | str | Unset = UNSET
    mission_type: str | Unset = 'consensus'
    status: None | str | Unset = UNSET
    team_size_min: int | Unset = 2
    team_size_max: int | Unset = 5
    assignment_mode: str | Unset = 'random'
    required_roles_json: list[str] | None | Unset = UNSET
    start_at: None | str | Unset = UNSET
    submission_due_at: None | str | Unset = UNSET
    rules_json: None | TeamMissionCreateRequestRulesJsonType0 | Unset = UNSET
    experiment_key: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.team_mission_create_request_rules_json_type_0 import TeamMissionCreateRequestRulesJsonType0
        title = self.title

        market = self.market

        mission_key: None | str | Unset
        if isinstance(self.mission_key, Unset):
            mission_key = UNSET
        else:
            mission_key = self.mission_key

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

        mission_type = self.mission_type

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        team_size_min = self.team_size_min

        team_size_max = self.team_size_max

        assignment_mode = self.assignment_mode

        required_roles_json: list[str] | None | Unset
        if isinstance(self.required_roles_json, Unset):
            required_roles_json = UNSET
        elif isinstance(self.required_roles_json, list):
            required_roles_json = self.required_roles_json


        else:
            required_roles_json = self.required_roles_json

        start_at: None | str | Unset
        if isinstance(self.start_at, Unset):
            start_at = UNSET
        else:
            start_at = self.start_at

        submission_due_at: None | str | Unset
        if isinstance(self.submission_due_at, Unset):
            submission_due_at = UNSET
        else:
            submission_due_at = self.submission_due_at

        rules_json: dict[str, Any] | None | Unset
        if isinstance(self.rules_json, Unset):
            rules_json = UNSET
        elif isinstance(self.rules_json, TeamMissionCreateRequestRulesJsonType0):
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
        if mission_key is not UNSET:
            field_dict["mission_key"] = mission_key
        if description is not UNSET:
            field_dict["description"] = description
        if symbol is not UNSET:
            field_dict["symbol"] = symbol
        if mission_type is not UNSET:
            field_dict["mission_type"] = mission_type
        if status is not UNSET:
            field_dict["status"] = status
        if team_size_min is not UNSET:
            field_dict["team_size_min"] = team_size_min
        if team_size_max is not UNSET:
            field_dict["team_size_max"] = team_size_max
        if assignment_mode is not UNSET:
            field_dict["assignment_mode"] = assignment_mode
        if required_roles_json is not UNSET:
            field_dict["required_roles_json"] = required_roles_json
        if start_at is not UNSET:
            field_dict["start_at"] = start_at
        if submission_due_at is not UNSET:
            field_dict["submission_due_at"] = submission_due_at
        if rules_json is not UNSET:
            field_dict["rules_json"] = rules_json
        if experiment_key is not UNSET:
            field_dict["experiment_key"] = experiment_key

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.team_mission_create_request_rules_json_type_0 import TeamMissionCreateRequestRulesJsonType0
        d = dict(src_dict)
        title = d.pop("title")

        market = d.pop("market")

        def _parse_mission_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_key = _parse_mission_key(d.pop("mission_key", UNSET))


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


        mission_type = d.pop("mission_type", UNSET)

        def _parse_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        status = _parse_status(d.pop("status", UNSET))


        team_size_min = d.pop("team_size_min", UNSET)

        team_size_max = d.pop("team_size_max", UNSET)

        assignment_mode = d.pop("assignment_mode", UNSET)

        def _parse_required_roles_json(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                required_roles_json_type_0 = cast(list[str], data)

                return required_roles_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        required_roles_json = _parse_required_roles_json(d.pop("required_roles_json", UNSET))


        def _parse_start_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        start_at = _parse_start_at(d.pop("start_at", UNSET))


        def _parse_submission_due_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        submission_due_at = _parse_submission_due_at(d.pop("submission_due_at", UNSET))


        def _parse_rules_json(data: object) -> None | TeamMissionCreateRequestRulesJsonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rules_json_type_0 = TeamMissionCreateRequestRulesJsonType0.from_dict(data)



                return rules_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TeamMissionCreateRequestRulesJsonType0 | Unset, data)

        rules_json = _parse_rules_json(d.pop("rules_json", UNSET))


        def _parse_experiment_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        experiment_key = _parse_experiment_key(d.pop("experiment_key", UNSET))


        team_mission_create_request = cls(
            title=title,
            market=market,
            mission_key=mission_key,
            description=description,
            symbol=symbol,
            mission_type=mission_type,
            status=status,
            team_size_min=team_size_min,
            team_size_max=team_size_max,
            assignment_mode=assignment_mode,
            required_roles_json=required_roles_json,
            start_at=start_at,
            submission_due_at=submission_due_at,
            rules_json=rules_json,
            experiment_key=experiment_key,
        )


        team_mission_create_request.additional_properties = d
        return team_mission_create_request

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
