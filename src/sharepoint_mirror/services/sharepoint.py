"""SharePoint client using Microsoft Graph API."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from flask import current_app


@dataclass
class DriveItem:
    """Represents a SharePoint drive item (file or folder)."""

    id: str
    name: str
    path: str
    is_folder: bool
    size: int | None
    mime_type: str | None
    web_url: str | None
    created_by: str | None
    last_modified_by: str | None
    created_at: str | None
    modified_at: str | None
    # For delta queries
    is_deleted: bool = False
    download_url: str | None = None


@dataclass
class Drive:
    """Represents a SharePoint document library (drive)."""

    id: str
    name: str
    web_url: str | None


class SharePointClient:
    """Client for Microsoft Graph API SharePoint operations."""

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    AUTH_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        site_hostname: str | None = None,
        site_path: str | None = None,
    ):
        """Initialize SharePoint client."""
        self.tenant_id = tenant_id or current_app.config["SHAREPOINT_TENANT_ID"]
        self.client_id = client_id or current_app.config["SHAREPOINT_CLIENT_ID"]
        self.client_secret = client_secret or current_app.config["SHAREPOINT_CLIENT_SECRET"]
        self.site_hostname = site_hostname or current_app.config["SHAREPOINT_SITE_HOSTNAME"]
        self.site_path = site_path or current_app.config["SHAREPOINT_SITE_PATH"]

        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._site_id: str | None = None

        self.timeout = current_app.config.get("SYNC_DOWNLOAD_TIMEOUT", 300)

    def _get_access_token(self) -> str:
        """Get or refresh access token using client credentials flow."""
        # Check if we have a valid token
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now(UTC) < self._token_expires_at - timedelta(minutes=5)
        ):
            return self._access_token

        # Get new token
        auth_url = self.AUTH_URL.format(tenant_id=self.tenant_id)
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(auth_url, data=data)
            response.raise_for_status()
            result = response.json()

        self._access_token = result["access_token"]
        expires_in = result.get("expires_in", 3600)
        self._token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return self._access_token

    def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make an authenticated request to Graph API."""
        token = self._get_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        timeout = kwargs.pop("timeout", self.timeout)

        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response

    def _get_site_id(self) -> str:
        """Get the SharePoint site ID."""
        if self._site_id:
            return self._site_id

        # Build site identifier: hostname:path
        site_identifier = f"{self.site_hostname}:{self.site_path}"
        url = f"{self.GRAPH_BASE_URL}/sites/{site_identifier}"

        response = self._request("GET", url)
        self._site_id = response.json()["id"]
        return self._site_id

    def get_drives(self) -> list[Drive]:
        """Get all document libraries (drives) for the site."""
        site_id = self._get_site_id()
        url = f"{self.GRAPH_BASE_URL}/sites/{site_id}/drives"

        response = self._request("GET", url)
        data = response.json()

        drives = []
        for item in data.get("value", []):
            drives.append(
                Drive(
                    id=item["id"],
                    name=item["name"],
                    web_url=item.get("webUrl"),
                )
            )
        return drives

    def get_drive_by_name(self, name: str) -> Drive | None:
        """Get a specific drive by name."""
        drives = self.get_drives()
        for drive in drives:
            if drive.name.lower() == name.lower():
                return drive
        return None

    def get_drive_items_delta(
        self,
        drive_id: str,
        delta_link: str | None = None,
    ) -> tuple[list[DriveItem], str]:
        """
        Get changed items using delta query.
        Returns (items, new_delta_link).
        """
        if delta_link:
            url: str | None = delta_link
        else:
            # Initial sync - get all items
            url = f"{self.GRAPH_BASE_URL}/drives/{drive_id}/root/delta"

        items: list[DriveItem] = []
        new_delta_link: str = ""
        while url:
            response = self._request("GET", url)
            data = response.json()

            for item in data.get("value", []):
                items.append(self._parse_drive_item(item, drive_id))

            # Check for next page or delta link
            url = data.get("@odata.nextLink")
            if not url:
                # No more pages, get the delta link for next sync
                new_delta_link = data.get("@odata.deltaLink", "")

        return items, new_delta_link

    def _parse_drive_item(self, item: dict, drive_id: str) -> DriveItem:
        """Parse a drive item from Graph API response."""
        # Check if deleted
        is_deleted = "deleted" in item

        # Get path from parentReference
        parent_ref = item.get("parentReference", {})
        parent_path = parent_ref.get("path", "")
        # Remove the drive root prefix (e.g., "/drives/{drive-id}/root:")
        if ":" in parent_path:
            parent_path = parent_path.split(":", 1)[1]
        if not parent_path:
            parent_path = "/"

        full_path = f"{parent_path}/{item['name']}".replace("//", "/")

        # Get created/modified by
        created_by = None
        if "createdBy" in item and "user" in item["createdBy"]:
            created_by = item["createdBy"]["user"].get("displayName")

        last_modified_by = None
        if "lastModifiedBy" in item and "user" in item["lastModifiedBy"]:
            last_modified_by = item["lastModifiedBy"]["user"].get("displayName")

        # Get download URL (for files)
        download_url = None
        if "file" in item:
            download_url = item.get("@microsoft.graph.downloadUrl")

        return DriveItem(
            id=item["id"],
            name=item["name"],
            path=full_path,
            is_folder="folder" in item,
            size=item.get("size"),
            mime_type=item.get("file", {}).get("mimeType"),
            web_url=item.get("webUrl"),
            created_by=created_by,
            last_modified_by=last_modified_by,
            created_at=item.get("createdDateTime"),
            modified_at=item.get("lastModifiedDateTime"),
            is_deleted=is_deleted,
            download_url=download_url,
        )

    def download_file(self, drive_id: str, item_id: str) -> bytes:
        """Download file content."""
        url = f"{self.GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content"
        response = self._request("GET", url, timeout=self.timeout)
        return response.content

    def download_file_by_url(self, download_url: str) -> bytes:
        """Download file using pre-authenticated download URL."""
        # Download URLs are pre-authenticated, no need for our token
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(download_url)
            response.raise_for_status()
            return response.content

    def test_connection(self) -> dict:
        """Test the connection and return site info."""
        site_id = self._get_site_id()
        url = f"{self.GRAPH_BASE_URL}/sites/{site_id}"
        response = self._request("GET", url)
        site_info = response.json()

        drives = self.get_drives()

        return {
            "site_id": site_id,
            "site_name": site_info.get("displayName"),
            "site_url": site_info.get("webUrl"),
            "drives": [{"id": d.id, "name": d.name} for d in drives],
        }
