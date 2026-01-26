"""
Script to attach JIRA issues to Qase cases using saved mappings from a previous import run.

This script reads the log file from a previous import to extract JIRA issues for each case,
then attaches them using the Qase External Issues API.
"""

import json
import re
import sys
import os
import requests
from pathlib import Path
from typing import List, Dict


def extract_jira_links_from_log(log_file_path: str) -> List[Dict]:
    """
    Extract JIRA links from log file.
    
    Returns:
        list: List of dicts with structure [{"case_id": 123, "external_issues": ["PROJ-456"]}, ...]
    """
    jira_links = []
    
    # Pattern to match: "Stored JIRA issues for case 2934474: ['VTUPF-275']"
    jira_pattern = re.compile(r'Stored JIRA issues for case (\d+): (\[.*?\])')
    
    print(f"Reading log file: {log_file_path}")
    
    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            jira_match = jira_pattern.search(line)
            if jira_match:
                case_id = int(jira_match.group(1))
                jira_list_str = jira_match.group(2)
                # Parse the list string like "['VTTP-569', 'VTTP-570']"
                try:
                    jira_issues = eval(jira_list_str)  # Safe here since we control the format
                    jira_links.append({
                        'case_id': case_id,
                        'external_issues': jira_issues
                    })
                except Exception as e:
                    print(f"Warning: Could not parse JIRA issues for case {case_id}: {jira_list_str} - {e}")
    
    return jira_links


def load_config(config_path: str) -> Dict:
    """Load config.json file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def attach_external_issues(api_base_url: str, api_token: str, project_code: str, 
                          external_issue_type: str, links: List[Dict]) -> bool:
    """
    Attach external issues to Qase cases.
    
    Args:
        api_base_url: Base URL for Qase API (e.g., "https://api.qase.io/v1")
        api_token: Qase API token
        project_code: Qase project code
        external_issue_type: Type of external issue (e.g., "jira-cloud")
        links: List of dicts with structure [{"case_id": 123, "external_issues": ["PROJ-456"]}, ...]
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not links:
        return True
    
    url = f'{api_base_url}/case/{project_code}/external-issue/attach'
    payload = {
        'type': external_issue_type,
        'links': links
    }
    
    headers = {
        'Token': api_token,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status'):
                return True
            else:
                print(f"API returned error: {result.get('error', 'Unknown error')}")
                return False
        else:
            print(f"HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception when attaching external issues: {e}")
        return False


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Attach JIRA issues to Qase cases from a previous import')
    parser.add_argument('--config', default='./config.json', help='Path to config.json file')
    parser.add_argument('--log', help='Path to log file (if not provided, uses most recent)')
    
    args = parser.parse_args()
    
    # Load config
    print(f"Loading config from: {args.config}")
    config = load_config(args.config)
    
    # Find log file if not provided
    if not args.log:
        log_dir = Path('logs')
        log_files = sorted(log_dir.glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            print("Error: No log files found in logs/ directory")
            return
        args.log = str(log_files[0])
        print(f"Using most recent log file: {args.log}")
    
    # Extract JIRA links from log
    print("\nExtracting JIRA links from log file...")
    jira_links = extract_jira_links_from_log(args.log)
    
    print(f"Found {len(jira_links)} cases with JIRA issues")
    
    if not jira_links:
        print("No JIRA links found in log file. Nothing to attach.")
        return
    
    # Get project code from config
    projects = config.get('projects', {}).get('import', [])
    if not projects:
        print("Error: No projects configured in config.json")
        return
    
    project_code = projects[0]  # Use first project
    print(f"\nUsing project code: {project_code}")
    
    # Build API base URL
    qase_config = config.get('qase', {})
    ssl = 'https://' if qase_config.get('ssl', True) else 'http://'
    main_host = qase_config.get('host', 'qase.io')
    delimiter = '-' if (qase_config.get('enterprise') and main_host != 'qase.io') else '.'
    api_base_url = f'{ssl}api{delimiter}{main_host}/v1'
    
    api_token = qase_config.get('api_token')
    if not api_token:
        print("Error: qase.api_token not found in config.json")
        return
    
    # Get external issue type from config
    external_issue_type = config.get('tests', {}).get('external_issues', {}).get('type', 'jira-cloud')
    batch_size = config.get('tests', {}).get('external_issues', {}).get('batch_size', 50)
    
    print(f"API Base URL: {api_base_url}")
    print(f"External issue type: {external_issue_type}")
    print(f"Batch size: {batch_size}")
    
    # Attach JIRA issues in batches
    print(f"\nAttaching JIRA issues to {len(jira_links)} cases...")
    total_attached = 0
    total_failed = 0
    
    for i in range(0, len(jira_links), batch_size):
        batch = jira_links[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        success = attach_external_issues(
            api_base_url,
            api_token,
            project_code,
            external_issue_type,
            batch
        )
        
        if success:
            total_attached += len(batch)
            print(f"[{project_code}][External Issues] Successfully attached batch {batch_num} ({len(batch)} cases)")
        else:
            total_failed += len(batch)
            print(f"[{project_code}][External Issues] Failed to attach batch {batch_num} ({len(batch)} cases)")
    
    print(f"\n[{project_code}][External Issues] Attachment complete: {total_attached} succeeded, {total_failed} failed")


if __name__ == '__main__':
    main()
