from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class RegisterIn(BaseModel):
    email: str
    username: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    username: str

    model_config = {"from_attributes": True}


class AccountOut(BaseModel):
    id: int
    platform: str
    account_name: Optional[str]
    platform_user_id: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PostCreate(BaseModel):
    platform: str
    account_id: int
    media_type: str = "post"  # reel | story | post | video | photo
    caption: Optional[str] = None
    tags: List[str] = []
    product_link: Optional[str] = None
    schedule_time: Optional[datetime] = None  # jadwal auto-post
    save_as_draft: bool = False  # True = simpan draft saja


class PostOut(BaseModel):
    id: int
    platform: str
    account_id: int
    media_type: str
    caption: Optional[str]
    tags: List[str]
    product_link: Optional[str]
    status: str
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    platform_post_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnalyticsOut(BaseModel):
    platform: str
    post_id: int
    platform_post_id: Optional[str]
    likes: Optional[int] = None
    comments: Optional[int] = None
    views: Optional[int] = None
    reach: Optional[int] = None
    shares: Optional[int] = None
    comments_list: List[dict] = []
    raw: dict = {}
