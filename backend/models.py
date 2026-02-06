from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class CouponObj(BaseModel):
    id: str
    company_name: str
    company_logo_url: Optional[str] = None
    profit_amount: str
    description: str
    expiry_date: Optional[datetime] = None
    code: Optional[str] = None
    source_email_id: str
    thread_id: Optional[str] = None
    category: Literal['Retail', 'Food', 'Tech', 'Travel', 'Other'] = 'Other'
    is_expired: bool = False

class ScanResult(BaseModel):
    status: Literal['scanning', 'completed', 'failed']
    found_coupons: list[CouponObj]
    scanned_count: int
