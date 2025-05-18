from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime, timedelta

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from flask import Flask, request, jsonify
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gsc-server")

SCOPES = ["https://www.googleapis.com/auth/webmasters"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_CLIENT_SECRETS_FILE = os.environ.get("GSC_OAUTH_CLIENT_SECRETS_FILE") or os.path.join(SCRIPT_DIR, "client_secrets.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
GSC_CREDENTIALS_PATH = os.environ.get("GSC_CREDENTIALS_PATH")
POSSIBLE_CREDENTIAL_PATHS = [
    GSC_CREDENTIALS_PATH,
    os.path.join(SCRIPT_DIR, "service_account_credentials.json"),
    os.path.join(os.getcwd(), "service_account_credentials.json"),
]
SKIP_OAUTH = os.environ.get("GSC_SKIP_OAUTH", "").lower() in ("true", "1", "yes")

@mcp.command("initialize")
def initialize(params=None):
    return {
        "capabilities": {
            "textDocumentSync": 1
        },
        "serverInfo": {
            "name": "mcp-gsc-server",
            "version": "1.0"
        }
    }

@app.route("/", methods=["GET", "POST"])
def handle_mcp():
    if request.method == "GET":
        return jsonify({"status": "MCP server is alive"}), 200
    try:
        data = request.get_json()
        result = mcp.handle_json(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

def get_gsc_service():
    if not SKIP_OAUTH:
        try:
            return get_gsc_service_oauth()
        except Exception:
            pass
    for cred_path in POSSIBLE_CREDENTIAL_PATHS:
        if cred_path and os.path.exists(cred_path):
            try:
                creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
                return build("searchconsole", "v1", credentials=creds)
            except Exception:
                continue
    raise FileNotFoundError("GSC credentials missing or invalid.")

def get_gsc_service_oauth():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CLIENT_SECRETS_FILE):
                raise FileNotFoundError("OAuth client secrets file missing.")
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
    return build("searchconsole", "v1", credentials=creds)

if __name__ == "__main__":
    USE_FLASK = os.getenv("USE_FLASK", "false").lower() == "true"
    if USE_FLASK:
        app = Flask(__name__)
        port = int(os.environ.get("PORT", 3000))
        app.run(host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")
