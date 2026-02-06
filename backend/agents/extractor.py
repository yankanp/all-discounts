import os
import json
import logging
import time
from typing import List, Optional, Generator, Any
from models import CouponObj
try:
    from openai import OpenAI, RateLimitError
except ImportError:
    OpenAI = None
    RateLimitError = Exception

class ExtractorAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key and OpenAI:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None
            logging.warning("OpenAI Client not initialized. Missing Key or Library.")

    def process_emails_gen(self, emails: List[dict]) -> Generator[dict, None, None]:
        """
        Generator that yields progress events and found coupons.
        Yields:
           {'type': 'log', 'msg': '...'}
           {'type': 'progress', 'percent': int}
           {'type': 'coupon', 'data': CouponObj}
        """
        seen_hashes = set()
        total = len(emails)

        for i, email in enumerate(emails):
            subject = email.get('subject', 'No Subject')
            # Yield Log
            yield {'type': 'log', 'msg': f"Scanning: {subject[:40]}..."}
            
            # Yield Progress
            percent = int(((i) / total) * 100)
            yield {'type': 'progress', 'percent': percent, 'msg': f"Scanning {i+1} of {total} emails..."}

            coupon = self._extract_single(email)
            if coupon:
                # Deduplication
                key = f"{coupon.company_name.lower().strip()}|{coupon.profit_amount.lower().strip()}|{coupon.code or ''}"
                
                if key in seen_hashes:
                    yield {'type': 'log', 'msg': f"  ↳ Skipping duplicate: {coupon.company_name}"}
                    continue
                
                seen_hashes.add(key)
                yield {'type': 'log', 'msg': f"  ✓ Found Deal: {coupon.company_name} ({coupon.profit_amount})"}
                yield {'type': 'coupon', 'data': coupon}
            
        yield {'type': 'progress', 'percent': 100, 'msg': "Finalizing results..."}

    def _extract_single(self, email: dict) -> Optional[CouponObj]:
        if not self.client:
            return None
        
        # Heuristic test
        if len(email.get('body', '')) < 50:
            return None

        prompt = f"""
        You are a highly intelligent Shopping & Opportunity Assistant Agent.
        Your goal is to extract TWO types of value from the email:
        1. COUPONS/DISCOUNTS (Standard retail offers)
        2. PAID SURVEYS/OPPORTUNITIES (Emails offering money/gift cards for feedback/surveys)
        
        Email Sender: {email.get('sender')}
        Email Subject: {email.get('subject')}
        Email Body (Truncated): {email.get('body')[:3000]} 

        Return valid JSON only. No markdown.
        Schema:
        {{
            "company_name": "string",
            "profit_amount": "string (e.g. 20% Off, $10 Credit, Earn $50, $5 Gift Card)",
            "description": "short summary of deal or survey opportunity",
            "expiry_date": "ISO8601 or null",
            "code": "coupon code or null",
            "category": "Retail, Food, Tech, Travel, Survey, or Other"
        }}
        
        For Surveys:
        - Set 'category' to 'Survey'.
        - Set 'profit_amount' to the reward amount (e.g. "$10 Reward").
        - If no clear monetary reward is stated, ignore it.
        
        If NO clear coupon/deal/paid-survey is found, return {{ "error": "not_found" }}.
        """

        max_retries = 3
        retry_delay = 2 

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o", 
                    messages=[{"role": "system", "content": "You are a JSON extractor."},
                              {"role": "user", "content": prompt}],
                    response_format={ "type": "json_object" } 
                )
                
                content = response.choices[0].message.content
                data = json.loads(content)

                if data.get("error") == "not_found":
                    return None
                
                return CouponObj(
                    id=email['id'],
                    company_name=data.get('company_name', 'Unknown'),
                    profit_amount=data.get('profit_amount', 'Deal'),
                    description=data.get('description', ''),
                    expiry_date=data.get('expiry_date'), 
                    code=data.get('code'),
                    source_email_id=email['id'],
                    thread_id=email.get('thread_id'), 
                    category=data.get('category', 'Other')
                )

            except RateLimitError:
                if attempt < max_retries - 1:
                    sleep_time = retry_delay * (2 ** attempt) 
                    # We can't log to generator output easily here without yielding, 
                    # but we can print for basic server logs
                    print(f"Rate limit hit. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    return None
            except Exception as e:
                logging.error(f"LLM Extraction failed for {email['id']}: {e}")
                return None
        
        return None
