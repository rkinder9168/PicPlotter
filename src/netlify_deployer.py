"""
Netlify deployment integration for PicPlotter Auto.

Deploys single-file HTML exports to Netlify for easy sharing with clients.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4


@dataclass
class DeployResult:
    """Result of a Netlify deployment."""

    success: bool
    url: Optional[str] = None
    deployment_id: Optional[str] = None
    error: Optional[str] = None


class NetlifyDeployer:
    """Deploy single-file HTML to Netlify."""

    API_BASE = "https://api.netlify.com/api/v1"
    SITE_NAME = "picplotter-maps"

    def __init__(self, token: str, site_id: Optional[str] = None):
        self.token = token
        self.site_id = site_id

    def deploy(self, html_content: str, project_name: str) -> DeployResult:
        """
        Deploy HTML content to Netlify.

        Args:
            html_content: The complete HTML file content
            project_name: Base name for the project (unused, kept for API compat)

        Returns:
            DeployResult with URL on success or error message on failure
        """
        try:
            site_id = self._ensure_site()
            return self._deploy_file(site_id, html_content)
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
                error_data = json.loads(error_body)
                error_msg = error_data.get("message", str(e))
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_msg = error_body or str(e)

            if e.code == 401:
                return DeployResult(
                    success=False,
                    error="Invalid or expired Netlify token. Please update in Options.",
                )
            elif e.code == 403:
                return DeployResult(
                    success=False,
                    error="Access denied. Check your Netlify token permissions.",
                )
            elif e.code == 429:
                return DeployResult(
                    success=False,
                    error="Rate limit exceeded. Please try again later.",
                )
            else:
                return DeployResult(
                    success=False,
                    error=f"Deployment failed: {error_msg}",
                )
        except urllib.error.URLError as e:
            if "timed out" in str(e).lower():
                return DeployResult(
                    success=False,
                    error="Deployment timed out. Please try again.",
                )
            return DeployResult(
                success=False,
                error="No internet connection. Please check your network.",
            )
        except Exception as e:
            return DeployResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )

    def _ensure_site(self) -> str:
        """Ensure a Netlify site exists, creating one if needed. Returns site_id."""
        if self.site_id:
            # Delete the old site and recreate to avoid stale CDN caching
            try:
                self._api_request("DELETE", f"/sites/{self.site_id}")
            except urllib.error.HTTPError:
                pass
            self.site_id = None

        # Create new site
        site_id = self._create_site(self.SITE_NAME)
        self.site_id = site_id

        # Persist site_id to config
        try:
            from src.config import set_netlify_site_id
            set_netlify_site_id(site_id)
        except Exception:
            pass

        return site_id

    def _create_site(self, name: str) -> str:
        """Create a Netlify site, retrying with a unique suffix on 422."""
        try:
            result = self._api_request("POST", "/sites", {"name": name})
            return result["id"]
        except urllib.error.HTTPError as e:
            if e.code == 422:
                # Name taken, retry with unique suffix
                unique_name = f"{name}-{uuid4().hex[:6]}"
                result = self._api_request("POST", "/sites", {"name": unique_name})
                return result["id"]
            raise

    def _deploy_file(self, site_id: str, html_content: str) -> DeployResult:
        """Deploy HTML content using the file digest API."""
        file_bytes = html_content.encode("utf-8")
        file_sha1 = hashlib.sha1(file_bytes).hexdigest()

        # _headers file to explicitly set MIME type
        headers_content = "/index.html\n  Content-Type: text/html; charset=utf-8\n"
        headers_bytes = headers_content.encode("utf-8")
        headers_sha1 = hashlib.sha1(headers_bytes).hexdigest()

        # Step 1: Create deploy with file digests
        deploy_body = {
            "files": {
                "/index.html": file_sha1,
                "/_headers": headers_sha1,
            },
        }
        result = self._api_request("POST", f"/sites/{site_id}/deploys", deploy_body)
        deploy_id = result["id"]
        required = result.get("required", [])

        # Step 2: Upload files that Netlify needs
        if file_sha1 in required:
            self._upload_file(deploy_id, "/index.html", file_bytes)
        if headers_sha1 in required:
            self._upload_file(deploy_id, "/_headers", headers_bytes)

        deploy_url = result.get("ssl_url") or result.get("deploy_ssl_url", "")
        return DeployResult(
            success=True,
            url=deploy_url,
            deployment_id=deploy_id,
        )

    def _upload_file(self, deploy_id: str, path: str, data: bytes) -> None:
        """Upload a single file to a deploy."""
        # Strip leading slash for the URL path
        url_path = path.lstrip("/")
        upload_url = f"{self.API_BASE}/deploys/{deploy_id}/files/{url_path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/octet-stream",
        }
        request = urllib.request.Request(
            upload_url,
            data=data,
            headers=headers,
            method="PUT",
        )
        with urllib.request.urlopen(request, timeout=120) as _resp:
            pass

    def _api_request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Make an authenticated API request to Netlify."""
        url = f"{self.API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        data = json.dumps(body).encode("utf-8") if body else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)


def verify_token(token: str) -> tuple[bool, str]:
    """
    Verify that a Netlify token is valid.

    Args:
        token: Netlify personal access token

    Returns:
        Tuple of (is_valid, message)
    """
    url = "https://api.netlify.com/api/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
    }

    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            full_name = result.get("full_name") or result.get("email") or "Unknown"
            return True, f"Connected as: {full_name}"

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid token"
        elif e.code == 403:
            return False, "Token lacks required permissions"
        return False, f"Verification failed: {e.code}"

    except urllib.error.URLError:
        return False, "No internet connection"

    except Exception as e:
        return False, f"Error: {str(e)}"
