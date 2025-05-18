@mcp.tool()
async def get_search_by_page_query(
    site_url: str,
    page_url: str,
    days: int = 28
) -> str:
    """
    Get search analytics data for a specific page, broken down by query.
    
    Args:
        site_url: The URL of the site in Search Console (must be exact match)
        page_url: The specific page URL to analyze
        days: Number of days to look back (default: 28)
    """
    try:
        service = get_gsc_service()
        
        # Calculate date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Build request with page filter
        request = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": ["query"],
            "dimensionFilterGroups": [{
                "filters": [{
                    "dimension": "page",
                    "operator": "equals",
                    "expression": page_url
                }]
            }],
            "rowLimit": 20,  # Top 20 queries for this page
            "orderBy": [{"metric": "CLICK_COUNT", "direction": "descending"}]
        }
        
        # Execute request
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        
        if not response.get("rows"):
            return f"No search data found for page {page_url} in the last {days} days."
        
        # Format results
        result_lines = [f"Search queries for page {page_url} (last {days} days):"]
        result_lines.append("\n" + "-" * 80 + "\n")
        
        # Create header
        result_lines.append("Query | Clicks | Impressions | CTR | Position")
        result_lines.append("-" * 80)
        
        # Add data rows
        for row in response.get("rows", []):
            query = row.get("keys", ["Unknown"])[0]
            clicks = row.get("clicks", 0)
            impressions = row.get("impressions", 0)
            ctr = row.get("ctr", 0) * 100
            position = row.get("position", 0)
            
            result_lines.append(f"{query[:100]} | {clicks} | {impressions} | {ctr:.2f}% | {position:.1f}")
        
        # Add total metrics
        total_clicks = sum(row.get("clicks", 0) for row in response.get("rows", []))
        total_impressions = sum(row.get("impressions", 0) for row in response.get("rows", []))
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        
        result_lines.append("-" * 80)
        result_lines.append(f"TOTAL | {total_clicks} | {total_impressions} | {avg_ctr:.2f}% | -")
        
        return "\n".join(result_lines)
    except Exception as e:
        return f"Error retrieving page query data: {str(e)}"from typing import Any, Dict, List, Optional
import os
import json
import sys
from datetime import datetime, timedelta
import asyncio
import inspect

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Eigene MCP-Implementierung
class MCP:
    def __init__(self, name):
        self.name = name
        self.tools = {}
    
    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator
    
    async def handle(self, data):
        try:
            # Debug-Ausgabe für eingehende Anfragen
            print(f"Received MCP request: {json.dumps(data)}", file=sys.stderr)
            
            if "method" in data and data["method"] == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {
                            "name": self.name,
                            "version": "1.0.0"
                        }
                    }
                }
                print(f"Sending initialize response: {json.dumps(response)}", file=sys.stderr)
                return response
            
            if "method" in data and data["method"] == "getMetadata":
                tools = []
                for name, func in self.tools.items():
                    sig = inspect.signature(func)
                    params = {}
                    required = []
                    
                    for param_name, param in sig.parameters.items():
                        if param_name == "self":
                            continue
                        
                        param_type = "string"
                        if param.annotation is int:
                            param_type = "integer"
                        elif param.annotation is bool:
                            param_type = "boolean"
                        
                        params[param_name] = {"type": param_type}
                        
                        if param.default is inspect.Parameter.empty:
                            required.append(param_name)
                    
                    doc = func.__doc__ or ""
                    tools.append({
                        "name": name,
                        "description": doc.strip(),
                        "parameters": {
                            "type": "object",
                            "properties": params,
                            "required": required
                        }
                    })
                    
                    # Debug-Ausgabe für jedes registrierte Tool
                    print(f"Registering tool: {name}", file=sys.stderr)
                
                # Debug-Ausgabe für die Gesamtzahl der Tools
                print(f"Total tools registered: {len(tools)}", file=sys.stderr)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "tools": tools
                    }
                }
                print(f"Sending getMetadata response with {len(tools)} tools", file=sys.stderr)
                return response
            
            if "method" in data and data["method"] == "execute":
                params = data.get("params", {})
                tool_name = params.get("name")
                tool_params = params.get("parameters", {})
                
                print(f"Executing tool: {tool_name} with params: {json.dumps(tool_params)}", file=sys.stderr)
                
                if tool_name not in self.tools:
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32601,
                            "message": f"Tool '{tool_name}' not found"
                        }
                    }
                    print(f"Tool not found: {tool_name}", file=sys.stderr)
                    return error_response
                
                tool_func = self.tools[tool_name]
                result = await tool_func(**tool_params)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "content": result
                    }
                }
                print(f"Tool execution completed: {tool_name}", file=sys.stderr)
                return response
            
            # Für resources/list-Anfragen, die vom mcp-remote-Tool gesendet werden
            if "method" in data and data["method"] == "resources/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "resources": []  # Leere Liste, da wir keine speziellen Ressourcen haben
                    }
                }
                print(f"Sending resources/list response", file=sys.stderr)
                return response
            
            error_response = {
                "jsonrpc": "2.0", 
                "id": data.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"Method '{data.get('method')}' not found"
                }
            }
            print(f"Method not found: {data.get('method')}", file=sys.stderr)
            return error_response
            
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "error": {
                    "code": -32000,
                    "message": str(e)
                }
            }
            print(f"Error handling request: {str(e)}", file=sys.stderr)
            return error_response
    
    def run(self, transport="stdio"):
        """
        Run the MCP server using the specified transport.
        
        Args:
            transport: The transport to use (currently only "stdio" is supported)
        """
        if transport != "stdio":
            raise ValueError(f"Unsupported transport: {transport}")
        
        import sys
        import json
        
        # Debug-Ausgabe
        print("MCP server started in stdio mode", file=sys.stderr)
        
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                    
                # Debug-Ausgabe
                print(f"Received: {line.strip()}", file=sys.stderr)
                
                # Parse the JSON request
                request = json.loads(line)
                
                # Handle the request asynchronously
                import asyncio
                response = asyncio.run(self.handle(request))
                
                # Send the response
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except Exception as e:
                print(f"Error in MCP server: {str(e)}", file=sys.stderr)
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32000,
                        "message": str(e)
                    }
                }) + "\n")
                sys.stdout.flush()

# Erstelle eine MCP-Instanz
mcp = MCP("gsc-server")

# Path to your service account JSON or user credentials JSON
# First check if GSC_CREDENTIALS_PATH environment variable is set
# Then try looking in the script directory and current working directory as fallbacks
GSC_CREDENTIALS_PATH = os.environ.get("GSC_CREDENTIALS_PATH")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSSIBLE_CREDENTIAL_PATHS = [
    GSC_CREDENTIALS_PATH,  # First try the environment variable if set
    os.path.join(SCRIPT_DIR, "service_account_credentials.json"),
    os.path.join(os.getcwd(), "service_account_credentials.json"),
    # Add any other potential paths here
]

# OAuth client secrets file path
OAUTH_CLIENT_SECRETS_FILE = os.environ.get("GSC_OAUTH_CLIENT_SECRETS_FILE")
if not OAUTH_CLIENT_SECRETS_FILE:
    OAUTH_CLIENT_SECRETS_FILE = os.path.join(SCRIPT_DIR, "client_secrets.json")

# Token file path for storing OAuth tokens
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

# Environment variable to skip OAuth authentication
SKIP_OAUTH = os.environ.get("GSC_SKIP_OAUTH", "").lower() in ("true", "1", "yes")

SCOPES = ["https://www.googleapis.com/auth/webmasters"]

def get_gsc_service():
    """
    Returns an authorized Search Console service object.
    First tries OAuth authentication, then falls back to service account.
    """
    # Try OAuth authentication first if not skipped
    if not SKIP_OAUTH:
        try:
            return get_gsc_service_oauth()
        except Exception as e:
            # If OAuth fails, try service account
            pass
    
    # Try service account authentication
    for cred_path in POSSIBLE_CREDENTIAL_PATHS:
        if cred_path and os.path.exists(cred_path):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    cred_path, scopes=SCOPES
                )
                return build("searchconsole", "v1", credentials=creds)
            except Exception as e:
                continue  # Try the next path if this one fails
    
    # If we get here, none of the authentication methods worked
    raise FileNotFoundError(
        f"Authentication failed. Please either:\n"
        f"1. Set up OAuth by placing a client_secrets.json file in the script directory, or\n"
        f"2. Set the GSC_CREDENTIALS_PATH environment variable or place a service account credentials file in one of these locations: "
        f"{', '.join([p for p in POSSIBLE_CREDENTIAL_PATHS[1:] if p])}"
    )

def get_gsc_service_oauth():
    """
    Returns an authorized Search Console service object using OAuth.
    """
    creds = None
    
    # Check if token file exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # If credentials don't exist or are invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Check if client secrets file exists
            if not os.path.exists(OAUTH_CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"OAuth client secrets file not found. Please place a client_secrets.json file in the script directory "
                    f"or set the GSC_OAUTH_CLIENT_SECRETS_FILE environment variable."
                )
            
            # Start OAuth flow
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Save the credentials for future use
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
    
    # Build and return the service
    return build("searchconsole", "v1", credentials=creds)

@mcp.tool()
async def list_properties() -> str:
    """
    Retrieves and returns the user's Search Console properties.
    """
    try:
        service = get_gsc_service()
        site_list = service.sites().list().execute()

        # site_list is typically something like:
        # {
        #   "siteEntry": [
        #       {"siteUrl": "...", "permissionLevel": "..."},
        #       ...
        #   ]
        # }
        sites = site_list.get("siteEntry", [])

        if not sites:
            return "No Search Console properties found."

        # Format the results for easy reading
        lines = []
        for site in sites:
            site_url = site.get("siteUrl", "Unknown")
            permission = site.get("permissionLevel", "Unknown permission")
            lines.append(f"- {site_url} ({permission})")

        return "\n".join(lines)
    except FileNotFoundError as e:
        return (
            "Error: Service account credentials file not found.\n\n"
            "To access Google Search Console, please:\n"
            "1. Create a service account in Google Cloud Console\n"
            "2. Download the JSON credentials file\n"
            "3. Save it as 'service_account_credentials.json' in the same directory as this script\n"
            "4. Share your GSC properties with the service account email"
        )
    except Exception as e:
        return f"Error retrieving properties: {str(e)}"

@mcp.tool()
async def add_site(site_url: str) -> str:
    """
    Add a site to your Search Console properties.
    
    Args:
        site_url: The URL of the site to add (must be exact match e.g. https://example.com, or https://www.example.com, or https://subdomain.example.com/path/, for domain properties use format: sc-domain:example.com)
    """
    try:
        service = get_gsc_service()
        
        # Add the site
        response = service.sites().add(siteUrl=site_url).execute()
        
        # Format the response
        result_lines = [f"Site {site_url} has been added to Search Console."]
        
        # Add permission level if available
        if "permissionLevel" in response:
            result_lines.append(f"Permission level: {response['permissionLevel']}")
        
        return "\n".join(result_lines)
    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8'))
        error_details = error_content.get('error', {})
        error_code = e.resp.status
        error_message = error_details.get('message', str(e))
        error_reason = error_details.get('errors', [{}])[0].get('reason', '')
        
        if error_code == 409:
            return f"Site {site_url} is already added to Search Console."
        elif error_code == 403:
            if error_reason == 'forbidden':
                return f"Error: You don't have permission to add this site. Please verify ownership first."
            elif error_reason == 'quotaExceeded':
                return f"Error: API quota exceeded. Please try again later."
            else:
                return f"Error: Permission denied. {error_message}"
        elif error_code == 400:
            if error_reason == 'invalidParameter':
                return f"Error: Invalid site URL format. Please check the URL format and try again."
            else:
                return f"Error: Bad request. {error_message}"
        elif error_code == 401:
            return f"Error: Unauthorized. Please check your credentials."
        elif error_code == 429:
            return f"Error: Too many requests. Please try again later."
        elif error_code == 500:
            return f"Error: Internal server error from Google Search Console API. Please try again later."
        elif error_code == 503:
            return f"Error: Service unavailable. Google Search Console API is currently down. Please try again later."
        else:
            return f"Error adding site (HTTP {error_code}): {error_message}"
    except Exception as e:
        return f"Error adding site: {str(e)}"

@mcp.tool()
async def delete_site(site_url: str) -> str:
    """
    Remove a site from your Search Console properties.
    
    Args:
        site_url: The URL of the site to remove (must be exact match e.g. https://example.com, or https://www.example.com, or https://subdomain.example.com/path/, for domain properties use format: sc-domain:example.com)
    """
    try:
        service = get_gsc_service()
        
        # Delete the site
        service.sites().delete(siteUrl=site_url).execute()
        
        return f"Site {site_url} has been removed from Search Console."
    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8'))
        error_details = error_content.get('error', {})
        error_code = e.resp.status
        error_message = error_details.get('message', str(e))
        error_reason = error_details.get('errors', [{}])[0].get('reason', '')
        
        if error_code == 404:
            return f"Site {site_url} was not found in Search Console."
        elif error_code == 403:
            if error_reason == 'forbidden':
                return f"Error: You don't have permission to remove this site."
            elif error_reason == 'quotaExceeded':
                return f"Error: API quota exceeded. Please try again later."
            else:
                return f"Error: Permission denied. {error_message}"
        elif error_code == 400:
            if error_reason == 'invalidParameter':
                return f"Error: Invalid site URL format. Please check the URL format and try again."
            else:
                return f"Error: Bad request. {error_message}"
        elif error_code == 401:
            return f"Error: Unauthorized. Please check your credentials."
        elif error_code == 429:
            return f"Error: Too many requests. Please try again later."
        elif error_code == 500:
            return f"Error: Internal server error from Google Search Console API. Please try again later."
        elif error_code == 503:
            return f"Error: Service unavailable. Google Search Console API is currently down. Please try again later."
        else:
            return f"Error removing site (HTTP {error_code}): {error_message}"
    except Exception as e:
        return f"Error removing site: {str(e)}"

@mcp.tool()
async def get_search_analytics(site_url: str, days: int = 28, dimensions: str = "query") -> str:
    """
    Get search analytics data for a specific property.
    
    Args:
        site_url: The URL of the site in Search Console (must be exact match)
        days: Number of days to look back (default: 28)
        dimensions: Dimensions to group by (default: query). Options: query, page, device, country, date
                   You can provide multiple dimensions separated by comma (e.g., "query,page")
    """
    try:
        service = get_gsc_service()
        
        # Calculate date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Parse dimensions
        dimension_list = [d.strip() for d in dimensions.split(",")]
        
        # Build request
        request = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": dimension_list,
            "rowLimit": 20  # Limit to top 20 results
        }
        
        # Execute request
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        
        if not response.get("rows"):
            return f"No search analytics data found for {site_url} in the last {days} days."
        
        # Format results
        result_lines = [f"Search analytics for {site_url} (last {days} days):"]
        result_lines.append("\n" + "-" * 80 + "\n")
        
        # Create header based on dimensions
        header = []
        for dim in dimension_list:
            header.append(dim.capitalize())
        header.extend(["Clicks", "Impressions", "CTR", "Position"])
        result_lines.append(" | ".join(header))
        result_lines.append("-" * 80)
        
        # Add data rows
        for row in response.get("rows", []):
            data = []
            # Add dimension values
            for dim_value in row.get("keys", []):
                data.append(dim_value[:100])  # Increased truncation limit to 100 characters
            
            # Add metrics
            data.append(str(row.get("clicks", 0)))
            data.append(str(row.get("impressions", 0)))
            data.append(f"{row.get('ctr', 0) * 100:.2f}%")
            data.append(f"{row.get('position', 0):.1f}")
            
            result_lines.append(" | ".join(data))
        
        return "\n".join(result_lines)
    except Exception as e:
        return f"Error retrieving search analytics: {str(e)}"

@mcp.tool()
async def get_site_details(site_url: str) -> str:
    """
    Get detailed information about a specific Search Console property.
    
    Args:
        site_url: The URL of the site in Search Console (must be exact match)
    """
    try:
        service = get_gsc_service()
        
        # Get site details
        site_info = service.sites().get(siteUrl=site_url).execute()
        
        # Format the results
        result_lines = [f"Site details for {site_url}:"]
        result_lines.append("-" * 50)
        
        # Add basic info
        result_lines.append(f"Permission level: {site_info.get('permissionLevel', 'Unknown')}")
        
        # Add verification info if available
        if "siteVerificationInfo" in site_info:
            verify_info = site_info["siteVerificationInfo"]
            result_lines.append(f"Verification state: {verify_info.get('verificationState', 'Unknown')}")
            
            if "verifiedUser" in verify_info:
                result_lines.append(f"Verified by: {verify_info['verifiedUser']}")
                
            if "verificationMethod" in verify_info:
                result_lines.append(f"Verification method: {verify_info['verificationMethod']}")
        
        # Add ownership info if available
        if "ownershipInfo" in site_info:
            owner_info = site_info["ownershipInfo"]
            result_lines.append("\nOwnership Information:")
            result_lines.append(f"Owner: {owner_info.get('owner', 'Unknown')}")
            
            if "verificationMethod" in owner_info:
                result_lines.append(f"Ownership verification: {owner_info['verificationMethod']}")
        
        return "\n".join(result_lines)
    except Exception as e:
        return f"Error retrieving site details: {str(e)}"

@mcp.tool()
async def get_sitemaps(site_url: str) -> str:
    """
    List all sitemaps for a specific Search Console property.
    
    Args:
        site_url: The URL of the site in Search Console (must be exact match)
    """
    try:
        service = get_gsc_service()
        
        # Get sitemaps list
        sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
        
        if not sitemaps.get("sitemap"):
            return f"No sitemaps found for {site_url}."
        
        # Format the results
        result_lines = [f"Sitemaps for {site_url}:"]
        result_lines.append("-" * 80)
        
        # Header
        result_lines.append("Path | Last Downloaded | Status | Indexed URLs | Errors")
        result_lines.append("-" * 80)
        
        # Add each sitemap
        for sitemap in sitemaps.get("sitemap", []):
            path = sitemap.get("path", "Unknown")
            last_downloaded = sitemap.get("lastDownloaded", "Never")
            
            # Format last downloaded date if it exists
            if last_downloaded != "Never":
                try:
                    # Convert to more readable format
                    dt = datetime.fromisoformat(last_downloaded.replace('Z', '+00:00'))
                    last_downloaded = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            status = "Valid"
            if "errors" in sitemap and sitemap["errors"] > 0:
                status = "Has errors"
            
            # Get counts
            warnings = sitemap.get("warnings", 0)
            errors = sitemap.get("errors", 0)
            
            # Get contents if available
            indexed_urls = "N/A"
            if "contents" in sitemap:
                for content in sitemap["contents"]:
                    if content.get("type") == "web":
                        indexed_urls = content.get("submitted", "0")
                        break
            
            result_lines.append(f"{path} | {last_downloaded} | {status} | {indexed_urls} | {errors}")
        
        return "\n".join(result_lines)
    except Exception as e:
        return f"Error retrieving sitemaps: {str(e)}"

@mcp.tool()
async def inspect_url_enhanced(site_url: str, page_url: str) -> str:
    """
    Enhanced URL inspection to check indexing status and rich results in Google.
    
    Args:
        site_url: The URL of the site in Search Console (must be exact match, for domain properties use format: sc-domain:example.com)
        page_url: The specific URL to inspect
    """
    try:
        service = get_gsc_service()
        
        # Build request
        request = {
            "inspectionUrl": page_url,
            "siteUrl": site_url
        }
        
        # Execute request
        response = service.urlInspection().index().inspect(body=request).execute()
        
        if not response or "inspectionResult" not in response:
            return f"No inspection data found for {page_url}."
        
        inspection = response["inspectionResult"]
        
        # Format the results
        result_lines = [f"URL Inspection for {page_url}:"]
        result_lines.append("-" * 80)
        
        # Add inspection result link if available
        if "inspectionResultLink" in inspection:
            result_lines.append(f"Search Console Link: {inspection['inspectionResultLink']}")
            result_lines.append("-" * 80)
        
        # Indexing status section
        index_status = inspection.get("indexStatusResult", {})
        verdict = index_status.get("verdict", "UNKNOWN")
        
        result_lines.append(f"Indexing Status: {verdict}")
        
        # Coverage state
        if "coverageState" in index_status:
            result_lines.append(f"Coverage: {index_status['coverageState']}")
        
        # Last crawl
        if "lastCrawlTime" in index_status:
            try:
                crawl_time = datetime.fromisoformat(index_status["lastCrawlTime"].replace('Z', '+00:00'))
                result_lines.append(f"Last Crawled: {crawl_time.strftime('%Y-%m-%d %H:%M')}")
            except:
                result_lines.append(f"Last Crawled: {index_status['lastCrawlTime']}")
        
        # Page fetch
        if "pageFetchState" in index_status:
            result_lines.append(f"Page Fetch: {index_status['pageFetchState']}")
        
        # Robots.txt status
        if "robotsTxtState" in index_status:
            result_lines.append(f"Robots.txt: {index_status['robotsTxtState']}")
        
        # Indexing state
        if "indexingState" in index_status:
            result_lines.append(f"Indexing State: {index_status['indexingState']}")
        
        # Canonical information
        if "googleCanonical" in index_status:
            result_lines.append(f"Google Canonical: {index_status['googleCanonical']}")
        
        if "userCanonical" in index_status and index_status.get("userCanonical") != index_status.get("googleCanonical"):
            result_lines.append(f"User Canonical: {index_status['userCanonical']}")
        
        # Crawled as
        if "crawledAs" in index_status:
            result_lines.append(f"Crawled As: {index_status['crawledAs']}")
        
        # Referring URLs
        if "referringUrls" in index_status and index_status["referringUrls"]:
            result_lines.append("\nReferring URLs:")
            for url in index_status["referringUrls"][:5]:  # Limit to 5 examples
                result_lines.append(f"- {url}")
            
            if len(index_status["referringUrls"]) > 5:
                result_lines.append(f"... and {len(index_status['referringUrls']) - 5} more")
        
        # Rich results
        if "richResultsResult" in inspection:
            rich = inspection["richResultsResult"]
            result_lines.append(f"\nRich Results: {rich.get('verdict', 'UNKNOWN')}")
            
            if "detectedItems" in rich and rich["detectedItems"]:
                result_lines.append("Detected Rich Result Types:")
                
                for item in rich["detectedItems"]:
                    rich_type = item.get("richResultType", "Unknown")
                    result_lines.append(f"- {rich_type}")
                    
                    # If there are items with names, show them
                    if "items" in item and item["items"]:
                        for i, subitem in enumerate(item["items"][:3]):  # Limit to 3 examples
                            if "name" in subitem:
                                result_lines.append(f"  • {subitem['name']}")
                        
                        if len(item["items"]) > 3:
                            result_lines.append(f"  • ... and {len(item['items']) - 3} more items")
            
            # Check for issues
            if "richResultsIssues" in rich and rich["richResultsIssues"]:
                result_lines.append("\nRich Results Issues:")
                for issue in rich["richResultsIssues"]:
                    severity = issue.get("severity", "Unknown")
                    message = issue.get("message", "Unknown issue")
                    result_lines.append(f"- [{severity}] {message}")
        
        return "\n".join(result_lines)
    except Exception as e:
        return f"Error inspecting URL: {str(e)}"

@mcp.tool()
async def batch_url_inspection(site_url: str, urls: str) -> str:
    """
    Inspect multiple URLs in batch (within API limits).
    
    Args:
        site_url: The URL of the site in Search Console (must be exact match, for domain properties use format: sc-domain:example.com)
        urls: List of URLs to inspect, one per line
    """
    try:
        service = get_gsc_service()
        
        # Parse URLs
        url_list = [url.strip() for url in urls.split('\n') if url.strip()]
        
        if not url_list:
            return "No URLs provided for inspection."
        
        if len(url_list) > 10:
            return f"Too many URLs provided ({len(url_list)}). Please limit to 10 URLs per batch to avoid API quota issues."
        
        # Process each URL
        results = []
        
        for page_url in url_list:
            # Build request
            request = {
                "inspectionUrl": page_url,
                "siteUrl": site_url
            }
            
            try:
                # Execute request with a small delay to avoid rate limits
                response = service.urlInspection().index().inspect(body=request).execute()
                
                if not response or "inspectionResult" not in response:
                    results.append(f"{page_url}: No inspection data found")
                    continue
                
                inspection = response["inspectionResult"]
                index_status = inspection.get("indexStatusResult", {})
                
                # Get key information
                verdict = index_status.get("verdict", "UNKNOWN")
                coverage = index_status.get("coverageState", "Unknown")
                last_crawl = "Never"
                
                if "lastCrawlTime" in index_status:
                    try:
                        crawl_time = datetime.fromisoformat(index_status["lastCrawlTime"].replace('Z', '+00:00'))
                        last_crawl = crawl_time.strftime('%Y-%m-%d')
                    except:
                        last_crawl = index_status["lastCrawlTime"]
                
                # Check for rich results
                rich_results = "None"
                if "richResultsResult" in inspection:
                    rich = inspection["richResultsResult"]
                    if rich.get("verdict") == "PASS" and "detectedItems" in rich and rich["detectedItems"]:
                        rich_types = [item.get("richResultType", "Unknown") for item in rich["detectedItems"]]
                        rich_results = ", ".join(rich_types)
                
                # Format result
                results.append(f"{page_url}:\n  Status: {verdict} - {coverage}\n  Last Crawl: {last_crawl}\n  Rich Results: {rich_results}\n")
            
            except Exception as e:
                results.append(f"{page_url}: Error - {str(e)}")
        
        # Combine results
        return f"Batch URL Inspection Results for {site_url}:\n\n" + "\n".join(results)
    
    except Exception as e:
        return f"Error performing batch inspection: {str(e)}"
