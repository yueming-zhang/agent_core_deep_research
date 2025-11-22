"""
Local Direct Google Calendar Access with OAuth2 3LO

This script demonstrates how to:
1. Load Google OAuth2 credentials from google_cred.json
2. Use a running OAuth2 callback server for authentication
3. Authenticate with Google using OAuth2 3-legged flow
4. Retrieve calendar events for the next 4 weeks

Requirements:
- google_cred.json with valid OAuth2 credentials
- oauth2_callback_server.py running on port 9090
- Google Calendar API access enabled in Google Cloud Console

Usage:
1. Start the OAuth2 callback server in a separate terminal:
   cd /workspaces/agent_core_deep_research/3lo.test
   python oauth2_callback_server.py --region us-west-2

2. Run this script:
   python 1_local_direct.py
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from oauth2_callback_server import (
    store_token_in_oauth2_callback_server,
    wait_for_oauth2_server_to_be_ready,
    get_oauth2_callback_url
)
# Allow OAuth2 over HTTP for local development
# WARNING: This should only be used for local development, never in production
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# Path to credentials file
SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR / 'google_cred.json'
TOKEN_FILE = SCRIPT_DIR / 'token.json'


def load_google_credentials():
    """
    Load Google OAuth2 credentials from google_cred.json
    
    Returns:
        dict: Google OAuth2 credentials configuration
    """
    print(f"Loading credentials from: {CREDENTIALS_FILE}")
    
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {CREDENTIALS_FILE}\n"
            "Please ensure google_cred.json exists in the same directory."
        )
    
    with open(CREDENTIALS_FILE, 'r') as f:
        creds_data = json.load(f)
    
    print("✓ Credentials loaded successfully")
    return creds_data


def check_oauth2_callback_server():
    """
    Check if the OAuth2 callback server is running and ready.
    
    Returns:
        bool: True if server is ready, False otherwise
    """
    print("Checking OAuth2 callback server status...")
    
    is_ready = wait_for_oauth2_server_to_be_ready()
    
    if not is_ready:
        print("\n✗ OAuth2 callback server is not running!")
        print("\nPlease start it in a separate terminal:")
        print("  cd /workspaces/agent_core_deep_research/3lo.test")
        print("  python oauth2_callback_server.py --region us-west-2")
        print()
        return False
    
    print("✓ OAuth2 callback server is ready")
    return True


def get_authenticated_credentials():
    """
    Authenticate with Google using OAuth2 flow.
    Uses token.json for cached credentials if available.
    
    Returns:
        Credentials: Authenticated Google OAuth2 credentials
    """
    creds = None
    
    # Check if we have cached credentials
    if TOKEN_FILE.exists():
        print("Found cached credentials in token.json")
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If credentials are invalid or don't exist, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("\nStarting OAuth2 authentication flow...")
            
            # Load credentials from google_cred.json
            creds_data = load_google_credentials()
            
            # Get the callback URL from the OAuth2 callback server
            callback_url = get_oauth2_callback_url()
            print(f"Using callback URL: {callback_url}")
            
            # Create OAuth2 flow using the oauth2_callback_server
            flow = InstalledAppFlow.from_client_config(
                creds_data,
                SCOPES,
                redirect_uri=callback_url
            )
            
            # Generate the authorization URL
            auth_url, state = flow.authorization_url(
                prompt='consent',
                access_type='offline'
            )
            
            print("\n" + "=" * 80)
            print("Please open this URL in your browser to authorize:")
            print(auth_url)
            print("=" * 80)
            print("\nAfter authorization, paste the full redirect URL here:")
            
            # Wait for user to paste the callback URL
            import webbrowser
            webbrowser.open(auth_url)
            
            redirect_response = input("\nPaste the redirect URL: ").strip()
            
            # Extract the authorization code from the redirect URL
            flow.fetch_token(authorization_response=redirect_response)
            
            # Get the credentials
            creds = flow.credentials
            
            # Store token in the OAuth2 callback server
            if creds.token:
                print("Storing token in OAuth2 callback server...")
                store_token_in_oauth2_callback_server(creds.token)
        
        # Save the credentials for future use
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        print("✓ Credentials saved to token.json")
    else:
        print("✓ Using valid cached credentials")
    
    return creds


def get_calendar_events(credentials, weeks=4):
    """
    Retrieve calendar events for the next specified number of weeks.
    
    Args:
        credentials: Authenticated Google OAuth2 credentials
        weeks (int): Number of weeks to retrieve events for (default: 4)
    
    Returns:
        list: List of calendar events
    """
    try:
        # Build the Calendar API service
        service = build('calendar', 'v3', credentials=credentials)
        
        # Calculate time range
        now = datetime.utcnow()
        end_date = now + timedelta(weeks=weeks)
        
        # Format dates for API (RFC3339 format)
        time_min = now.isoformat() + 'Z'
        time_max = end_date.isoformat() + 'Z'
        
        print(f"\nFetching calendar events from {now.date()} to {end_date.date()}")
        print(f"(Next {weeks} weeks)\n")
        
        # Call the Calendar API
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=100,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            print('No upcoming events found.')
            return []
        
        print(f"Found {len(events)} events:\n")
        print("=" * 80)
        
        # Display events
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', '(No title)')
            
            # Parse and format the start time
            if 'T' in start:
                # DateTime event
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %I:%M %p')
            else:
                # All-day event
                formatted_time = f"{start} (All day)"
            
            print(f"• {formatted_time}")
            print(f"  {summary}")
            
            # Show location if available
            if 'location' in event:
                print(f"  Location: {event['location']}")
            
            # Show description if available (truncated)
            if 'description' in event:
                desc = event['description']
                if len(desc) > 100:
                    desc = desc[:97] + '...'
                print(f"  Description: {desc}")
            
            print()
        
        print("=" * 80)
        
        return events
        
    except HttpError as error:
        print(f'An error occurred: {error}')
        return []


def main():
    """
    Main function to orchestrate the calendar retrieval process.
    Expects oauth2_callback_server.py to be running in a separate terminal.
    """
    print("=" * 80)
    print("Google Calendar - Retrieve Next 4 Weeks Events")
    print("=" * 80)
    print()
    
    try:
        # Step 1: Load credentials configuration
        load_google_credentials()
        
        # Step 2: Check if the OAuth2 callback server is running
        if not check_oauth2_callback_server():
            return 1
        
        # Step 3: Authenticate and get credentials
        creds = get_authenticated_credentials()
        
        # Step 4: Retrieve calendar events
        events = get_calendar_events(creds, weeks=4)
        
        print(f"\n✓ Successfully retrieved {len(events)} calendar events")
        
    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
