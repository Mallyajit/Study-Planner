"""
Media Handler for WhatsApp Messages
Downloads and processes images and PDFs from Twilio media URLs
"""

import os
import requests
from typing import Optional, Dict
from datetime import datetime


class MediaHandler:
    """Handle WhatsApp media downloads (images, PDFs)"""
    
    def __init__(self, twilio_account_sid: str, twilio_auth_token: str, upload_dir: str = "uploads"):
        """
        Initialize media handler
        
        Args:
            twilio_account_sid: Twilio account SID
            twilio_auth_token: Twilio auth token
            upload_dir: Directory to save downloaded media
        """
        self.account_sid = twilio_account_sid
        self.auth_token = twilio_auth_token
        self.upload_dir = upload_dir
        
        # Create uploads directory if it doesn't exist
        os.makedirs(upload_dir, exist_ok=True)
        print(f"✓ Media Handler initialized (uploads: {upload_dir})")
    
    def download_media(self, media_url: str, media_content_type: str) -> Optional[Dict]:
        """
        Download media from Twilio URL
        
        Args:
            media_url: URL of the media file
            media_content_type: MIME type (e.g., 'image/jpeg', 'application/pdf')
        
        Returns:
            Dict with file info or None if failed
        """
        try:
            # Determine file extension from content type
            extension_map = {
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'application/pdf': '.pdf',
                'image/heic': '.heic',
                'image/heif': '.heif'
            }
            
            extension = extension_map.get(media_content_type.lower(), '.bin')
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"media_{timestamp}{extension}"
            filepath = os.path.join(self.upload_dir, filename)
            
            # Download media with authentication
            response = requests.get(
                media_url,
                auth=(self.account_sid, self.auth_token),
                timeout=30
            )
            
            if response.status_code == 200:
                # Save file
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                file_size = len(response.content)
                
                print(f"✓ Downloaded media: {filename} ({file_size} bytes)")
                
                return {
                    'filename': filename,
                    'filepath': filepath,
                    'content_type': media_content_type,
                    'size': file_size,
                    'extension': extension
                }
            else:
                print(f"✗ Failed to download media: HTTP {response.status_code}")
                return None
        
        except Exception as e:
            print(f"✗ Error downloading media: {e}")
            return None
    
    def is_image(self, content_type: str) -> bool:
        """Check if content type is an image"""
        return content_type.lower().startswith('image/')
    
    def is_pdf(self, content_type: str) -> bool:
        """Check if content type is a PDF"""
        return content_type.lower() == 'application/pdf'
    
    def is_supported_media(self, content_type: str) -> bool:
        """Check if media type is supported for flashcard generation"""
        return self.is_image(content_type) or self.is_pdf(content_type)
    
    def cleanup_old_files(self, days: int = 7):
        """
        Delete media files older than specified days
        
        Args:
            days: Number of days to keep files
        """
        try:
            import time
            current_time = time.time()
            max_age = days * 24 * 60 * 60  # Convert days to seconds
            
            deleted_count = 0
            for filename in os.listdir(self.upload_dir):
                filepath = os.path.join(self.upload_dir, filename)
                if os.path.isfile(filepath):
                    file_age = current_time - os.path.getmtime(filepath)
                    if file_age > max_age:
                        os.remove(filepath)
                        deleted_count += 1
            
            if deleted_count > 0:
                print(f"✓ Cleaned up {deleted_count} old media files")
        
        except Exception as e:
            print(f"✗ Error cleaning up old files: {e}")
