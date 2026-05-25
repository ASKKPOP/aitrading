from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.challenge_submission_request_prediction_json_type_0 import ChallengeSubmissionRequestPredictionJsonType0





T = TypeVar("T", bound="ChallengeSubmissionRequest")



@_attrs_define
class ChallengeSubmissionRequest:
    """ 
        Attributes:
            submission_type (str | Unset):  Default: 'manual'.
            content (None | str | Unset):
            prediction_json (ChallengeSubmissionRequestPredictionJsonType0 | None | Unset):
            signal_id (int | None | Unset):
     """

    submission_type: str | Unset = 'manual'
    content: None | str | Unset = UNSET
    prediction_json: ChallengeSubmissionRequestPredictionJsonType0 | None | Unset = UNSET
    signal_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.challenge_submission_request_prediction_json_type_0 import ChallengeSubmissionRequestPredictionJsonType0
        submission_type = self.submission_type

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        prediction_json: dict[str, Any] | None | Unset
        if isinstance(self.prediction_json, Unset):
            prediction_json = UNSET
        elif isinstance(self.prediction_json, ChallengeSubmissionRequestPredictionJsonType0):
            prediction_json = self.prediction_json.to_dict()
        else:
            prediction_json = self.prediction_json

        signal_id: int | None | Unset
        if isinstance(self.signal_id, Unset):
            signal_id = UNSET
        else:
            signal_id = self.signal_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if submission_type is not UNSET:
            field_dict["submission_type"] = submission_type
        if content is not UNSET:
            field_dict["content"] = content
        if prediction_json is not UNSET:
            field_dict["prediction_json"] = prediction_json
        if signal_id is not UNSET:
            field_dict["signal_id"] = signal_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.challenge_submission_request_prediction_json_type_0 import ChallengeSubmissionRequestPredictionJsonType0
        d = dict(src_dict)
        submission_type = d.pop("submission_type", UNSET)

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))


        def _parse_prediction_json(data: object) -> ChallengeSubmissionRequestPredictionJsonType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                prediction_json_type_0 = ChallengeSubmissionRequestPredictionJsonType0.from_dict(data)



                return prediction_json_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChallengeSubmissionRequestPredictionJsonType0 | None | Unset, data)

        prediction_json = _parse_prediction_json(d.pop("prediction_json", UNSET))


        def _parse_signal_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        signal_id = _parse_signal_id(d.pop("signal_id", UNSET))


        challenge_submission_request = cls(
            submission_type=submission_type,
            content=content,
            prediction_json=prediction_json,
            signal_id=signal_id,
        )


        challenge_submission_request.additional_properties = d
        return challenge_submission_request

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
