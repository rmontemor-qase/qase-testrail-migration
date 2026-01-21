import requests
import json
from typing import List, Dict, Any


class QaseApiClient:
    """Qase API client for direct HTTP calls (bypasses SDK validation)."""
    
    def __init__(self, base_url: str, api_token: str, logger=None, max_retries: int = 3, backoff_factor: int = 1):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.logger = logger
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        self.headers = {
            'Token': api_token,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def create_cases_bulk(self, project_code: str, cases: List[Dict[str, Any]]) -> bool:
        """Create test cases in bulk (used for cases with shared steps)."""
        url = f"{self.base_url}/case/{project_code}/bulk"
        payload = {"cases": cases}
        
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                
                if response.status_code == 200:
                    if self.logger:
                        self.logger.log(f"Successfully created {len(cases)} cases with shared steps")
                    return True
                elif response.status_code == 401:
                    if self.logger:
                        self.logger.log(f"Failed to create cases with shared steps: {response.status_code} - {response.text}", 'error')
                    return False
                elif response.status_code >= 500 and attempt < self.max_retries:
                    if self.logger:
                        self.logger.log(f"Server error ({response.status_code}), retrying... (attempt {attempt + 1}/{self.max_retries})")
                    import time
                    time.sleep(self.backoff_factor * (2 ** attempt))
                    continue
                else:
                    if self.logger:
                        self.logger.log(f"Failed to create cases with shared steps: {response.status_code} - {response.text}", 'error')
                        if cases:
                            self.logger.log(f"Request payload (first case): {json.dumps(cases[0], indent=2, default=str)}", 'error')
                    return False
                    
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries:
                    if self.logger:
                        self.logger.log(f"Request exception, retrying... (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                    import time
                    time.sleep(self.backoff_factor * (2 ** attempt))
                    continue
                else:
                    if self.logger:
                        self.logger.log(f"Failed to create cases with shared steps after {self.max_retries} retries: {str(e)}", 'error')
                    return False
        
        return False
