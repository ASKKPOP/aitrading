from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.team_submission_request_prediction_json_type_0 import TeamSubmissionRequestPredictionJsonType0





T = TypeVar("T", bound="TeamSubmissionRequest")



@_attrs_define
class TeamSubmissionRequest:
    """ 
        Attributes:
            title (str):
            content (str):
            prediction_json (None | TeamSubmissionRequestPredictionJsonType0 | Unset):
            confidence (float | None | Unset):
     """

    title: str
    content: str
    prediction_json: None | TeamSubmissionRequestPredictionJsonType0 | Unset = UNSET
    confidence: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.team_submission_request_prediction_json_type_0 import TeamSubmissionRequestPredictionJsonType0
        title = self.title

        content = self.content

        prediction_json: dict[str, Any] | None | Unset
        if isinstance(self.prediction_json, Unset):
            prediction_json = UNSET
        elif isinstance(self.prediction_json, TeamSubmissionRequestPredictionJsonType0):
            prediction_json = self.prediction_json.to_dict()
        else:
            prediction_json = self.prediction_json

        confidence: float | None | Unset
        if isinstance(self.confidence, Unset):
            confidence = UNSET
        else:
            confidence = self.confidence


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "title": title,
            "content": content,
        })
        if prediction_json is not UNSET:
            field_dict["prediction_json"] = prediction_json
        if confidence is not UNSET:
            field_dict["confidence"] = confidence

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.team_submission_request_prediction_json_type_0 import TeamSubmissionRequestPredictionJsonType0
        d = dict(src_dict)
        title = d.pop("title")

        content = d.pop("content")

        def _parse_prediction_json(data: object) -> None | TeamSubmissionRequestPredictionJsonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                prediction_json_type_0 = TeamSubmissionRequestPredictionJsonType0.from_dict(data)



                return prediction_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TeamSubmissionRequestPredictionJsonType0 | Unset, data)

        prediction_json = _parse_prediction_json(d.pop("prediction_json", UNSET))


        def _parse_confidence(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        confidence = _parse_confidence(d.pop("confidence", UNSET))


        team_submission_request = cls(
            title=title,
            content=content,
            prediction_json=prediction_json,
            confidence=confidence,
        )


        team_submission_request.additional_properties = d
        return team_submission_request

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
