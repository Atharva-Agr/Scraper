from typing import List, Optional
from pydantic import BaseModel, Field


# -----------------------------
# Output schema
# -----------------------------

class HotelInfo(BaseModel):
    hotel_name: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    area: Optional[str] = Field(default=None)
    chain_or_independent: Optional[str] = Field(default=None)
    hotel_type: Optional[str] = Field(default=None)
    website: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    rating: Optional[str] = Field(default=None)
    review_summary: Optional[str] = Field(default=None)
    room_types: List[str] = Field(default_factory=list)
    room_pricing: List[str] = Field(default_factory=list)
    facilities: List[str] = Field(default_factory=list)
    source_url: Optional[str] = Field(default=None)

class ContactInfo(BaseModel):
    name: Optional[str] = Field(default=None)
    role: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    linkedin_url: Optional[str] = Field(default=None)
    profile_url: Optional[str] = Field(default=None)
    source_url: Optional[str] = Field(default=None)


class ContactResults(BaseModel):
    contacts: List[ContactInfo] = Field(default_factory=list)
