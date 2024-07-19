from flask import Flask, redirect, url_for, session, request, render_template
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.analytics.admin import AnalyticsAdminServiceClient
from google.analytics.admin_v1alpha.types import ListAccountSummariesRequest
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest

import json
import os
from dotenv import load_dotenv


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Load environment variables from .env file
load_dotenv()

CLIENT_SECRET_FILE = os.getenv('CLIENT_SECRET_FILE')
REDIRECT_URI = 'https://localhost:5000/callback'
SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']

flow = Flow.from_client_secrets_file(
    CLIENT_SECRET_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

CUSTOMER_CREDENTIALS_FILE = os.getenv('CUSTOMER_CREDENTIALS_FILE')

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/customer_login')
def customer_login():
    authorization_url, state = flow.authorization_url(
        access_type='online',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    print(f"Session state: {session.get('state')}")
    print(f"Request state: {request.args.get('state')}")

    try:
        flow.fetch_token(authorization_response=request.url)

        if session.get('state') != request.args.get('state'):
            print("State mismatch!")
            return redirect(url_for('index'))

        credentials = flow.credentials
        session['credentials'] = credentials_to_dict(credentials)

        properties = get_analytics_properties(credentials)
        if not properties:
            return "No Google Analytics properties found for this user.", 404

        session['properties'] = properties

        return redirect(url_for('select_property'))

    except Exception as e:
        print(f"Error in callback: {e}")
        return f"An error occurred during the callback: {str(e)}", 500

@app.route('/select_property')
def select_property():
    properties = session.get('properties')
    if not properties:
        return "No properties available", 400

    return render_template('select_property.html', properties=properties)

@app.route('/fetch_data_from_property', methods=['POST'])
def fetch_data_from_property():
    property_id = request.form['property_id']
    credentials_dict = session.get('credentials')
    credentials = Credentials(
        token=credentials_dict['token'],
        refresh_token=credentials_dict['refresh_token'],
        token_uri=credentials_dict['token_uri'],
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=credentials_dict['scopes']
    )

    analytics_data = fetch_google_analytics_data(credentials, property_id)
    print(f"Fetched Analytics Data: {analytics_data}")  # Debugging output

    if not analytics_data:
        return "No data found for the selected property.", 404

    return render_template('analytics.html', data=analytics_data)


def save_customer_credentials(customer_email, credentials_dict):
    try:
        with open(CUSTOMER_CREDENTIALS_FILE, 'r') as f:
            customer_credentials = json.load(f)
    except FileNotFoundError:
        customer_credentials = {}

    customer_credentials[customer_email] = credentials_dict

    with open(CUSTOMER_CREDENTIALS_FILE, 'w') as f:
        json.dump(customer_credentials, f)

    print(f"Saved credentials for {customer_email}: {credentials_dict}")

def load_customer_credentials():
    try:
        with open(CUSTOMER_CREDENTIALS_FILE, 'r') as f:
            credentials = json.load(f)
            print(f"Loaded customer credentials: {credentials}")
            return credentials
    except FileNotFoundError:
        return {}

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def get_analytics_properties(credentials):
    try:
        client = AnalyticsAdminServiceClient(credentials=credentials)
        request = ListAccountSummariesRequest()
        response = client.list_account_summaries(request)

        properties = []
        for account in response.account_summaries:
            for property in account.property_summaries:
                properties.append({
                    'property_id': property.property,
                    'property_name': property.display_name
                })
        
        print("Collected properties:")
        for prop in properties:
            print(prop)

        return properties
    except Exception as e:
        print(f"Error fetching Google Analytics properties: {e}")
        return []

def fetch_google_analytics_data(credentials, property_id):
    try:
        client = BetaAnalyticsDataClient(credentials=credentials)
        
        request = RunReportRequest(
            property='{property_id}',
            dimensions=[{'name': 'date'}],
            metrics=[{'name': 'activeUsers'}],
            date_ranges=[{'start_date': '7daysAgo', 'end_date': 'today'}]
        )
        
        response = client.run_report(request)
        
        data = []
        for row in response.rows:
            data.append({
                'date': row.dimension_values[0].value,
                'active_users': row.metric_values[0].value
            })
        
        return data
    except Exception as e:
        print(f"Error fetching Google Analytics data: {e}")
        return []

@app.route('/logout')
def logout():
    clear_customer_credentials()
    session.clear()
    return redirect(url_for('index'))

def clear_customer_credentials():
    customer_credentials_file = os.getenv('CUSTOMER_CREDENTIALS_FILE')
    
    with open(customer_credentials_file, 'w') as f:
        json.dump({}, f)

if __name__ == '__main__':
    app.run(debug=True, ssl_context=(r'C:\Users\dell\cert.pem', r'C:\Users\dell\key.pem'))
