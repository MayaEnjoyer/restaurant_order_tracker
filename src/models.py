from dataclasses import dataclass
from typing import Literal

Role = Literal["admin", "user"]

@dataclass(frozen=True)
class UserDTO:
    user_id: int
    username: str
    role: Role
