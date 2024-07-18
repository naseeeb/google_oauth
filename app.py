from flask import Flask, redirect, url_for, session, request, render_template
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import json
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)


CLIENT_SECRET_FILE = r'D:\gapsmith\google_analytics\client_secret1.json'
REDIRECT_URI = 'https://localhost:5000/callback'
SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']


flow = Flow.from_client_secrets_file(
    CLIENT_SECRET_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

# Path to store customer credentials
CUSTOMER_CREDENTIALS_FILE = r'D:\gapsmith\google_analytics\customer_credentials.json'

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

        if session.get('customer_email'):
            save_customer_credentials(session['customer_email'], credentials_to_dict(credentials))
            session.pop('customer_email', None)
            return redirect(url_for('owner_view'))

        views = get_analytics_views(credentials)
        if not views:
            accounts_exist = check_google_analytics_accounts_exist(credentials)
            if accounts_exist:
                return "No Google Analytics web properties found for this user.", 403
            else:
                return "No Google Analytics accounts found for this user.", 404

        return render_template('select_view.html', views=views)

    except Exception as e:
        print(f"Error in callback: {e}")
        return f"An error occurred during the callback: {str(e)}", 500

@app.route('/owner_request')
def owner_request():
    return render_template('owner_request.html')

@app.route('/request_customer_data', methods=['POST'])
def request_customer_data():
    customer_email = request.form['customer_email']
    print(f"Customer email: {customer_email}")  
    session['customer_email'] = customer_email

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        login_hint=customer_email  
    )
    print(f"Authorization URL: {authorization_url}")  
    session['state'] = state
    return redirect(authorization_url)

@app.route('/owner_view')
def owner_view():
    customers = load_customer_credentials()
    return render_template('owner_view.html', customers=customers)

@app.route('/fetch_customer_data', methods=['POST'])
def fetch_customer_data():
    customer_id = request.form['customer_id']
    credentials_dict = load_customer_credentials().get(customer_id)
    credentials = Credentials(
        token=credentials_dict['token'],
        refresh_token=credentials_dict['refresh_token'],
        token_uri=credentials_dict['token_uri'],
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=credentials_dict['scopes']
    )

    view_id = request.form['view_id']
    analytics_data = fetch_google_analytics_data(credentials, view_id)

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

def get_analytics_views(credentials):
    service = build('analytics', 'v3', credentials=credentials)

    try:
        accounts = service.management().accounts().list().execute()
        if not accounts.get('items'):
            return []
        account_id = accounts['items'][0]['id']

        properties = service.management().webproperties().list(accountId=account_id).execute()
        if not properties.get('items'):
            return []
        property_id = properties['items'][0]['id']

        profiles = service.management().profiles().list(
            accountId=account_id,
            webPropertyId=property_id
        ).execute()

        return profiles['items']
    except Exception as e:
        print(f"Error fetching Google Analytics views: {e}")
        return []

def check_google_analytics_accounts_exist(credentials):
    service = build('analytics', 'v3', credentials=credentials)

    try:
        accounts = service.management().accounts().list().execute()
        return bool(accounts.get('items'))
    except Exception as e:
        print(f"Error checking Google Analytics accounts: {e}")
        return False

def fetch_google_analytics_data(credentials, view_id):
    creds = Credentials(
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        scopes=credentials.scopes
    )

    service = build('analytics', 'v3', credentials=creds)

    try:
        results = service.data().ga().get(
            ids=f'ga:{view_id}',
            start_date='7daysAgo',
            end_date='today',
            metrics='ga:sessions'
        ).execute()

        data = results.get('rows', [])
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
    customer_credentials_file = r'D:\gapsmith\google_analytics\customer_credentials.json'
    
    
    with open(customer_credentials_file, 'w') as f:
        json.dump({}, f)

if __name__ == '__main__':
    app.run(debug=True, ssl_context=(r'C:\Users\dell\cert.pem', r'C:\Users\dell\key.pem'))
