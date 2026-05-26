from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.agent_register_positions_type_0_item import AgentRegisterPositionsType0Item





T = TypeVar("T", bound="AgentRegister")



@_attrs_define
class AgentRegister:
    """ 
        Attributes:
            name (str):
            password (str):
            wallet_address (None | str | Unset):
            initial_balance (float | Unset):  Default: 100000.0.
            positions (list[AgentRegisterPositionsType0Item] | None | Unset):
     """

    name: str
    password: str
    wallet_address: None | str | Unset = UNSET
    initial_balance: float | Unset = 100000.0
    positions: list[AgentRegisterPositionsType0Item] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_register_positions_type_0_item import AgentRegisterPositionsType0Item
        name = self.name

        password = self.password

        wallet_address: None | str | Unset
        if isinstance(self.wallet_address, Unset):
            wallet_address = UNSET
        else:
            wallet_address = self.wallet_address

        initial_balance = self.initial_balance

        positions: list[dict[str, Any]] | None | Unset
        if isinstance(self.positions, Unset):
            positions = UNSET
        elif isinstance(self.positions, list):
            positions = []
            for positions_type_0_item_data in self.positions:
                positions_type_0_item = positions_type_0_item_data.to_dict()
                positions.append(positions_type_0_item)


        else:
            positions = self.positions


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
            "password": password,
        })
        if wallet_address is not UNSET:
            field_dict["wallet_address"] = wallet_address
        if initial_balance is not UNSET:
            field_dict["initial_balance"] = initial_balance
        if positions is not UNSET:
            field_dict["positions"] = positions

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_register_positions_type_0_item import AgentRegisterPositionsType0Item
        d = dict(src_dict)
        name = d.pop("name")

        password = d.pop("password")

        def _parse_wallet_address(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        wallet_address = _parse_wallet_address(d.pop("wallet_address", UNSET))


        initial_balance = d.pop("initial_balance", UNSET)

        def _parse_positions(data: object) -> list[AgentRegisterPositionsType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                positions_type_0 = []
                _positions_type_0 = data
                for positions_type_0_item_data in (_positions_type_0):
                    positions_type_0_item = AgentRegisterPositionsType0Item.from_dict(positions_type_0_item_data)



                    positions_type_0.append(positions_type_0_item)

                return positions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[AgentRegisterPositionsType0Item] | None | Unset, data)

        positions = _parse_positions(d.pop("positions", UNSET))


        agent_register = cls(
            name=name,
            password=password,
            wallet_address=wallet_address,
            initial_balance=initial_balance,
            positions=positions,
        )


        agent_register.additional_properties = d
        return agent_register

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
