"""
Local NAS Storage Backend

Implements the StorageBackend interface for local NAS file system access.
Used as fallback, testing backend, or primary storage on Synology DS923+.

Features:
- Direct file system I/O (no API calls)
- Path-based folder navigation
- Fastest performance (local disk I/O)
- Works offline (no network calls)
- Ideal for temporary/archive storage

Performance:
- Read/write: 50-100MB/s (NAS RAID performance)
- No API rate limits
- Suitable for all workloads (unlimited requests)

Constraints:
- Requires mounted volume access (e.g., /volume1/)
- No access control beyond file permissions
- No folder sharing/collaboration features
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional
from datetime import datetime
from glob import glob

from src.storage import StorageBackend

logger = logging.getLogger(__name__)


class LocalNASBackend(StorageBackend):
    """
    Local NAS (Network Attached Storage) backend implementation.
    
    Designed for Synology DS923+ with mounted volumes at /volume1/.
    Falls back to /tmp for development/testing.
    
    Folder IDs are absolute or relative paths:
    - "/volume1/Inbox" (absolute)
    - "Inbox" (relative to NAS root)
    
    Credential Format:
    {
        "path": "/volume1/",           # Base path on NAS
        "username": "admin",           # Optional: for authentication
        "check_permissions": true      # Optional: verify read/write
    }
    """
    
    def __init__(self):
        """Initialize Local NAS backend."""
        self.base_path: Optional[Path] = None
        self.credentials = None
    
    async def authenticate(self, credentials: Dict[str, str]) -> bool:
        """
        Authenticate with local NAS using path and optional permissions check.
        
        Args:
            credentials: {
                "path": "/volume1/",
                "username": "admin",
                "check_permissions": true
            }
        
        Returns:
            True if path is accessible
        
        Raises:
            ValueError: If path invalid or inaccessible
            PermissionError: If user lacks permissions
        """
        try:
            path_str = credentials.get("path", "/volume1/")
            
            if not path_str:
                raise ValueError("credentials['path'] cannot be empty")
            
            # Convert to Path object and expand ~ if needed
            base_path = Path(path_str).expanduser().resolve()
            
            # Verify path exists
            if not base_path.exists():
                raise FileNotFoundError(f"NAS path does not exist: {base_path}")
            
            # Verify it's a directory
            if not base_path.is_dir():
                raise ValueError(f"Path is not a directory: {base_path}")
            
            # Optional: check read/write permissions
            if credentials.get("check_permissions"):
                # Test read permission
                if not os.access(base_path, os.R_OK):
                    raise PermissionError(f"No read permission on {base_path}")
                
                # Test write permission
                if not os.access(base_path, os.W_OK):
                    raise PermissionError(f"No write permission on {base_path}")
            
            self.base_path = base_path
            self.credentials = credentials
            
            logger.info(
                "Local NAS backend authenticated",
                extra={
                    "path": str(base_path),
                    "username": credentials.get("username", "default"),
                    "has_write": os.access(base_path, os.W_OK)
                }
            )
            return True
            
        except (FileNotFoundError, PermissionError, ValueError) as e:
            logger.error("Local NAS authentication failed", extra={"error": str(e)})
            raise
        except Exception as e:
            logger.error("Unexpected error during NAS authentication", extra={"error": str(e)})
            raise
    
    async def list_folders(self) -> List[Dict[str, str]]:
        """
        List all subdirectories in the base path.
        
        Returns:
            List of folder dicts: [
                {"id": "/volume1/Inbox", "name": "Inbox", "path": "/volume1/Inbox"},
                ...
            ]
        
        Raises:
            ConnectionError: If base path doesn't exist
        """
        if not self.base_path:
            raise ConnectionError("Not authenticated. Call authenticate() first.")
        
        try:
            folders = []
            
            # List immediate subdirectories
            for item in self.base_path.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    folders.append({
                        "id": str(item),  # Absolute path as ID
                        "name": item.name,
                        "path": str(item)
                    })
            
            # Sort by name for consistency
            folders.sort(key=lambda x: x["name"])
            
            logger.info(
                "Listed NAS folders",
                extra={"base_path": str(self.base_path), "count": len(folders)}
            )
            return folders
            
        except Exception as e:
            logger.error("Failed to list NAS folders", extra={"error": str(e)})
            raise ConnectionError(f"Failed to list NAS folders: {str(e)}")
    
    async def upload_file(
        self,
        folder_id: str,
        filename: str,
        file: BinaryIO
    ) -> str:
        """
        Upload a file to NAS folder.
        
        Args:
            folder_id: Absolute or relative path to folder
            filename: Name for file (e.g., "document_2026-08-17.pdf")
            file: Binary file stream
        
        Returns:
            file_id: Absolute path to file
        
        Raises:
            FileNotFoundError: If folder doesn't exist
            ValueError: If filename or file invalid
            PermissionError: If no write access
        """
        if not self.base_path:
            raise ConnectionError("Not authenticated.")
        
        try:
            if not filename:
                raise ValueError("filename cannot be empty")
            
            if not folder_id:
                raise ValueError("folder_id cannot be empty")
            
            # Resolve folder path
            folder_path = Path(folder_id)
            if not folder_path.is_absolute():
                folder_path = self.base_path / folder_path
            
            folder_path = folder_path.resolve()
            
            # Security: ensure folder is within base_path
            if not str(folder_path).startswith(str(self.base_path)):
                raise PermissionError(f"Path escape detected: {folder_path}")
            
            # Verify folder exists
            if not folder_path.exists():
                raise FileNotFoundError(f"Folder does not exist: {folder_path}")
            
            if not folder_path.is_dir():
                raise ValueError(f"Path is not a directory: {folder_path}")
            
            # Write file
            file_path = folder_path / filename
            
            # Read from input stream and write to disk
            with open(file_path, "wb") as out_file:
                # Copy in chunks to handle large files
                while True:
                    chunk = file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    out_file.write(chunk)
            
            logger.info(
                "Uploaded file to NAS",
                extra={
                    "filename": filename,
                    "folder_id": folder_id,
                    "size": file_path.stat().st_size
                }
            )
            return str(file_path)
            
        except Exception as e:
            logger.error(
                "NAS upload failed",
                extra={"filename": filename, "folder_id": folder_id, "error": str(e)}
            )
            raise
    
    async def download_file(self, file_id: str) -> BinaryIO:
        """
        Download a file from NAS.
        
        Args:
            file_id: Absolute path to file
        
        Returns:
            BinaryIO: File stream
        
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If no read access
        """
        if not self.base_path:
            raise ConnectionError("Not authenticated.")
        
        try:
            if not file_id:
                raise ValueError("file_id cannot be empty")
            
            file_path = Path(file_id).resolve()
            
            # Security: ensure file is within base_path
            if not str(file_path).startswith(str(self.base_path)):
                raise PermissionError(f"Path escape detected: {file_path}")
            
            # Verify file exists
            if not file_path.exists():
                raise FileNotFoundError(f"File does not exist: {file_path}")
            
            if not file_path.is_file():
                raise ValueError(f"Path is not a file: {file_path}")
            
            # Read file into BytesIO stream
            from io import BytesIO
            file_stream = BytesIO()
            
            with open(file_path, "rb") as in_file:
                # Copy in chunks
                while True:
                    chunk = in_file.read(1024 * 1024)
                    if not chunk:
                        break
                    file_stream.write(chunk)
            
            file_stream.seek(0)  # Reset to beginning for reading
            
            logger.info(
                "Downloaded file from NAS",
                extra={"file_id": file_id, "size": file_path.stat().st_size}
            )
            return file_stream
            
        except Exception as e:
            logger.error("NAS download failed", extra={"file_id": file_id, "error": str(e)})
            raise
    
    async def list_files(
        self,
        folder_id: str,
        pattern: str = "*.pdf"
    ) -> List[Dict[str, str]]:
        """
        List files in a NAS folder.
        
        Args:
            folder_id: Absolute or relative path to folder
            pattern: File pattern (e.g., "*.pdf")
        
        Returns:
            List of file dicts
        
        Raises:
            FileNotFoundError: If folder doesn't exist
        """
        if not self.base_path:
            raise ConnectionError("Not authenticated.")
        
        try:
            # Resolve folder path
            folder_path = Path(folder_id)
            if not folder_path.is_absolute():
                folder_path = self.base_path / folder_path
            
            folder_path = folder_path.resolve()
            
            # Security check
            if not str(folder_path).startswith(str(self.base_path)):
                raise PermissionError(f"Path escape detected: {folder_path}")
            
            if not folder_path.exists():
                raise FileNotFoundError(f"Folder does not exist: {folder_path}")
            
            if not folder_path.is_dir():
                raise ValueError(f"Path is not a directory: {folder_path}")
            
            # List files matching pattern
            files = []
            for file_path in sorted(folder_path.glob(pattern)):
                if file_path.is_file():
                    stat = file_path.stat()
                    files.append({
                        "id": str(file_path),
                        "name": file_path.name,
                        "size": str(stat.st_size),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z"
                    })
            
            logger.info(
                "Listed NAS files",
                extra={
                    "folder_id": folder_id,
                    "pattern": pattern,
                    "count": len(files)
                }
            )
            return files
            
        except Exception as e:
            logger.error(
                "NAS file listing failed",
                extra={"folder_id": folder_id, "error": str(e)}
            )
            raise
    
    async def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from NAS.
        
        Args:
            file_id: Absolute path to file
        
        Returns:
            True if deletion succeeded
        
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If no delete access
        """
        if not self.base_path:
            raise ConnectionError("Not authenticated.")
        
        try:
            if not file_id:
                raise ValueError("file_id cannot be empty")
            
            file_path = Path(file_id).resolve()
            
            # Security check
            if not str(file_path).startswith(str(self.base_path)):
                raise PermissionError(f"Path escape detected: {file_path}")
            
            if not file_path.exists():
                raise FileNotFoundError(f"File does not exist: {file_path}")
            
            if not file_path.is_file():
                raise ValueError(f"Path is not a file: {file_path}")
            
            # Delete file
            file_path.unlink()
            
            logger.info("Deleted file from NAS", extra={"file_id": file_id})
            return True
            
        except Exception as e:
            logger.error("NAS deletion failed", extra={"file_id": file_id, "error": str(e)})
            raise
    
    async def get_storage_info(self) -> Dict[str, str]:
        """
        Get NAS storage info.
        
        Returns:
            Dict with account, usage, quota, etc.
        """
        if not self.base_path:
            raise ConnectionError("Not authenticated.")
        
        try:
            # Get disk usage statistics
            import shutil
            stat = shutil.disk_usage(self.base_path)
            
            return {
                "account": self.credentials.get("username", "local"),
                "used_bytes": str(stat.used),
                "total_bytes": str(stat.total),
                "backend_type": "local_nas"
            }
            
        except Exception as e:
            logger.error("Failed to get NAS storage info", extra={"error": str(e)})
            raise


__all__ = ["LocalNASBackend"]
