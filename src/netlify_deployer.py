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
from typing import Dict, Optional
from uuid import uuid4

from src.config import get_ssl_context


@dataclass
class DeployResult:
    """Result of a Netlify deployment."""

    success: bool
    url: Optional[str] = None
    deployment_id: Optional[str] = None
    site_id: Optional[str] = None
    error: Optional[str] = None


class NetlifyDeployer:
    """Deploy single-file HTML to Netlify."""

    API_BASE = "https://api.netlify.com/api/v1"
    SITE_NAME = "picplotter-maps"

    def __init__(self, token: str, site_id: Optional[str] = None):
        self.token = token
        self.site_id = site_id

    def deploy(
        self,
        html_content: str,
        project_name: str,
        extra_files: Optional[Dict[str, bytes]] = None,
    ) -> DeployResult:
        """
        Deploy HTML content to Netlify.

        Args:
            html_content: The complete HTML file content
            project_name: Base name for the project (unused, kept for API compat)
            extra_files: Optional extra assets to deploy alongside index.html,
                keyed by site-absolute path (e.g. "/media/clip.mp4") -> bytes.
                Used to ship local video files referenced by the HTML.

        Returns:
            DeployResult with URL on success or error message on failure
        """
        try:
            site_id = self._ensure_site()
            result = self._deploy_file(site_id, html_content, extra_files)
            if result.success:
                result.site_id = site_id
            return result
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
        """Ensure a Netlify site exists. Reuses self.site_id if it still exists on Netlify;
        otherwise creates a new site. Never deletes — that would break live client links."""
        if self.site_id:
            try:
                self._api_request("GET", f"/sites/{self.site_id}")
                return self.site_id
            except urllib.error.HTTPError as e:
                if e.code not in (404, 410):
                    raise
                # Site no longer exists on Netlify; fall through and create a new one.
                self.site_id = None

        site_id = self._create_site()
        self.site_id = site_id
        return site_id

    def _create_site(self) -> str:
        """Create a Netlify site with a unique name."""
        unique_name = f"{self.SITE_NAME}-{uuid4().hex[:8]}"
        result = self._api_request("POST", "/sites", {"name": unique_name})
        return result["id"]

    def _deploy_file(
        self,
        site_id: str,
        html_content: str,
        extra_files: Optional[Dict[str, bytes]] = None,
    ) -> DeployResult:
        """Deploy HTML content (plus any extra asset files) using the digest API."""
        file_bytes = html_content.encode("utf-8")
        file_sha1 = hashlib.sha1(file_bytes).hexdigest()

        # _headers file to explicitly set MIME type
        headers_content = "/index.html\n  Content-Type: text/html; charset=utf-8\n"
        headers_bytes = headers_content.encode("utf-8")
        headers_sha1 = hashlib.sha1(headers_bytes).hexdigest()

        # Map every file (index, headers, extra assets) to its sha1 digest.
        contents: Dict[str, bytes] = {
            "/index.html": file_bytes,
            "/_headers": headers_bytes,
        }
        for path, data in (extra_files or {}).items():
            contents[path] = data
        digests = {path: hashlib.sha1(data).hexdigest() for path, data in contents.items()}

        # Step 1: Create deploy with file digests
        result = self._api_request("POST", f"/sites/{site_id}/deploys", {"files": digests})
        deploy_id = result["id"]
        required = set(result.get("required", []))

        # Step 2: Upload only the files Netlify says it still needs
        for path, data in contents.items():
            if digests[path] in required:
                self._upload_file(deploy_id, path, data)

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
        with urllib.request.urlopen(request, timeout=120, context=get_ssl_context()) as _resp:
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

        with urllib.request.urlopen(request, timeout=30, context=get_ssl_context()) as response:
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
        with urllib.request.urlopen(request, timeout=30, context=get_ssl_context()) as response:
            result = json.loads(response.read().decode("utf-8"))
            full_name = result.get("full_name") or result.get("email") or "Unknown"
            return True, f"Connected as: {full_name}"

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid token"
        elif e.code == 403:
            return False, "Token lacks required permissions"
        return False, f"Verification failed: {e.code}"

    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        reason_text = str(reason) or repr(reason)
        if "CERTIFICATE_VERIFY_FAILED" in reason_text or "SSL" in reason_text.upper():
            return False, f"SSL certificate verification failed (try installing certifi): {reason_text}"
        if "timed out" in reason_text.lower():
            return False, "Connection to api.netlify.com timed out"
        return False, f"Could not reach api.netlify.com: {reason_text}"

    except Exception as e:
        return False, f"Error: {type(e).__name__}: {e}"
