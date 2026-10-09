from pydantic import BaseModel, Field


class VoterLogin(BaseModel):
    matric_no: str
    password: str


class MobileVoterLogin(VoterLogin):
    device_id: str = Field(min_length=8, max_length=100)
    device_name: str = ""


class AdminLogin(BaseModel):
    username: str
    password: str


class VoteIn(BaseModel):
    selections: dict[int, int]  # {position_id: candidate_id}


class PositionIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    display_order: int = 0


class CandidateIn(BaseModel):
    position_id: int
    full_name: str = Field(min_length=1, max_length=120)
    department: str = ""
    level: str = ""
    manifesto: str = ""
    photo_url: str = ""


class StatusIn(BaseModel):
    status: str  # draft | open | closed


class ResetIn(BaseModel):
    confirm: str
