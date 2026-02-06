from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
from typing import List, Dict, Optional

class GmailService:
    def __init__(self, token_info: Dict):
        """
        Initialize with the OAuth token info dict.
        Expects: {'access_token': '...', 'refresh_token': '...', ...}
        """
        self.creds = Credentials.from_authorized_user_info(token_info)
        self.service = build('gmail', 'v1', credentials=self.creds)

    def fetch_promotional_emails(self, max_results: int = 60, months_back: int = 6, start_timestamp: Optional[float] = None) -> List[Dict]:
        """
        Fetches the latest emails from 'CATEGORY_PROMOTIONS'.
        If start_timestamp is provided, fetches emails received after that time.
        Otherwise falls back to months_back.
        """
        try:
            if start_timestamp:
                # Gmail 'after' accepts seconds since epoch
                query = f'category:promotions after:{int(start_timestamp)}'
            else:
                query = f'category:promotions newer_than:{months_back}m'
                
            results = self.service.users().messages().list(
                userId='me', 
                q=query, 
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            email_data = []

            if not messages:
                print("No promotional emails found.")
                return []

            for msg in messages:
                full_msg = self.service.users().messages().get(
                    userId='me', 
                    id=msg['id'], 
                    format='full'
                ).execute()
                
                parsed = self._parse_email(full_msg)
                if parsed:
                    email_data.append(parsed)
            
            return email_data

        except Exception as e:
            print(f"Error fetching emails: {str(e)}")
            raise e

    def _parse_email(self, msg_payload: Dict) -> Optional[Dict]:
        """
        Extracts details + Thread ID for deep linking.
        """
        try:
            payload = msg_payload.get('payload', {})
            headers = payload.get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
            date = next((h['value'] for h in headers if h['name'] == 'Date'), "")
            sender = next((h['value'] for h in headers if h['name'] == 'From'), "")
            
            # Thread ID is at the top level of the message resource
            thread_id = msg_payload.get('threadId')

            # Get Body (Text or HTML)
            body = ""
            parts = payload.get('parts', [])
            
            if not parts:
                data = payload.get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
            else:
                for part in parts:
                    if part['mimeType'] == 'text/plain' or part['mimeType'] == 'text/html':
                         data = part['body'].get('data', '')
                         if data:
                             body = base64.urlsafe_b64decode(data).decode('utf-8')
                             break 
            
            return {
                'id': msg_payload['id'],
                'thread_id': thread_id, # return thread_id for correct linking
                'subject': subject,
                'date': date,
                'sender': sender,
                'body': body
            }

        except Exception as e:
            print(f"Error parsing specific email: {str(e)}")
            return None
