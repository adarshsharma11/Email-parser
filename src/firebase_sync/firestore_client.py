"""
Firebase Firestore client for syncing vacation rental booking data.
"""
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from typing import Optional, Dict, Any, List
import structlog

from ..utils.models import BookingData, SyncResult
from ..utils.logger import get_logger
from config.settings import firebase_config, app_config


class FirestoreClient:
    """Firebase Firestore client for booking data synchronization."""
    
    def __init__(self):
        self.logger = get_logger("firestore_client")
        self.db: Optional[firestore.Client] = None
        self.initialized = False
    
    def initialize(self) -> bool:
        """
        Initialize Firebase Admin SDK and Firestore client.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            if not self.initialized:
                # Get Firebase credentials
                cred_dict = firebase_config.get_credentials_dict()
                
                # Check if credentials are valid
                if not cred_dict.get('project_id'):
                    self.logger.error("Firebase project ID not configured")
                    return False
                
                # Initialize Firebase Admin SDK
                if not firebase_admin._apps:
                    cred = credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                
                # Get Firestore client
                self.db = firestore.client()
                self.initialized = True
                
                self.logger.info("Firebase Firestore client initialized successfully",
                               project_id=firebase_config.project_id)
                return True
            else:
                return True
                
        except Exception as e:
            self.logger.error("Failed to initialize Firebase Firestore", error=str(e))
            self.initialized = False
            return False
    
    def sync_booking(self, booking_data: BookingData, dry_run: bool = False) -> SyncResult:
        """
        Sync booking data to Firestore.
        
        Args:
            booking_data: Booking data to sync
            dry_run: If True, don't actually write to Firestore
            
        Returns:
            SyncResult with operation status
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return SyncResult(
                        success=False,
                        error_message="Failed to initialize Firestore client",
                        reservation_id=booking_data.reservation_id
                    )
            
            # Check if booking already exists
            existing_booking = self._get_booking_by_reservation_id(
                booking_data.reservation_id
            )
            
            if existing_booking:
                self.logger.info("Booking already exists in Firestore",
                               reservation_id=booking_data.reservation_id)
                return SyncResult(
                    success=True,
                    is_new=False,
                    booking_data=booking_data,
                    reservation_id=booking_data.reservation_id
                )
            
            if dry_run:
                self.logger.info("DRY RUN: Would add new booking to Firestore",
                               reservation_id=booking_data.reservation_id)
                return SyncResult(
                    success=True,
                    is_new=True,
                    booking_data=booking_data,
                    reservation_id=booking_data.reservation_id
                )
            
            # Add new booking to Firestore
            booking_dict = booking_data.to_dict()
            booking_dict['updated_at'] = datetime.utcnow().isoformat()
            
            # Use reservation ID as document ID to prevent duplicates
            doc_ref = self.db.collection(app_config.bookings_collection).document(
                booking_data.reservation_id
            )
            doc_ref.set(booking_dict)
            
            self.logger.info("Successfully added booking to Firestore",
                           reservation_id=booking_data.reservation_id,
                           platform=booking_data.platform.value)
            
            return SyncResult(
                success=True,
                is_new=True,
                booking_data=booking_data,
                reservation_id=booking_data.reservation_id
            )
            
        except Exception as e:
            self.logger.error("Error syncing booking to Firestore",
                            reservation_id=booking_data.reservation_id,
                            error=str(e))
            return SyncResult(
                success=False,
                error_message=str(e),
                reservation_id=booking_data.reservation_id
            )
    
    def sync_bookings(
        self, 
        bookings: List[BookingData], 
        dry_run: bool = False
    ) -> List[SyncResult]:
        """
        Sync multiple bookings to Firestore.
        
        Args:
            bookings: List of booking data to sync
            dry_run: If True, don't actually write to Firestore
            
        Returns:
            List of SyncResult objects
        """
        results = []
        
        for booking in bookings:
            result = self.sync_booking(booking, dry_run)
            results.append(result)
        
        return results
    
    def get_booking_by_reservation_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get booking by reservation ID.
        
        Args:
            reservation_id: Reservation ID to search for
            
        Returns:
            Booking data dictionary or None if not found
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return None
            
            doc_ref = self.db.collection(app_config.bookings_collection).document(
                reservation_id
            )
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                return None
                
        except Exception as e:
            self.logger.error("Error getting booking by reservation ID",
                            reservation_id=reservation_id,
                            error=str(e))
            return None
    
    def get_bookings_by_platform(
        self, 
        platform: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get bookings by platform.
        
        Args:
            platform: Platform name to filter by
            limit: Maximum number of results to return
            
        Returns:
            List of booking data dictionaries
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return []
            
            query = self.db.collection(app_config.bookings_collection).where(
                'platform', '==', platform
            ).order_by('created_at', direction=firestore.Query.DESCENDING)
            
            if limit:
                query = query.limit(limit)
            
            docs = query.stream()
            bookings = [doc.to_dict() for doc in docs]
            
            self.logger.info("Retrieved bookings by platform",
                           platform=platform,
                           count=len(bookings))
            
            return bookings
            
        except Exception as e:
            self.logger.error("Error getting bookings by platform",
                            platform=platform,
                            error=str(e))
            return []
    
    def get_bookings_by_date_range(
        self, 
        start_date: datetime, 
        end_date: datetime,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get bookings within a date range.
        
        Args:
            start_date: Start date for range
            end_date: End date for range
            limit: Maximum number of results to return
            
        Returns:
            List of booking data dictionaries
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return []
            
            query = self.db.collection(app_config.bookings_collection).where(
                'check_in_date', '>=', start_date.isoformat()
            ).where(
                'check_in_date', '<=', end_date.isoformat()
            ).order_by('check_in_date')
            
            if limit:
                query = query.limit(limit)
            
            docs = query.stream()
            bookings = [doc.to_dict() for doc in docs]
            
            self.logger.info("Retrieved bookings by date range",
                           start_date=start_date.isoformat(),
                           end_date=end_date.isoformat(),
                           count=len(bookings))
            
            return bookings
            
        except Exception as e:
            self.logger.error("Error getting bookings by date range",
                            start_date=start_date.isoformat(),
                            end_date=end_date.isoformat(),
                            error=str(e))
            return []
    
    def update_booking(
        self, 
        reservation_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update an existing booking.
        
        Args:
            reservation_id: Reservation ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return False
            
            # Add updated timestamp
            updates['updated_at'] = datetime.utcnow().isoformat()
            
            doc_ref = self.db.collection(app_config.bookings_collection).document(
                reservation_id
            )
            doc_ref.update(updates)
            
            self.logger.info("Successfully updated booking",
                           reservation_id=reservation_id)
            return True
            
        except Exception as e:
            self.logger.error("Error updating booking",
                            reservation_id=reservation_id,
                            error=str(e))
            return False
    
    def delete_booking(self, reservation_id: str) -> bool:
        """
        Delete a booking from Firestore.
        
        Args:
            reservation_id: Reservation ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return False
            
            doc_ref = self.db.collection(app_config.bookings_collection).document(
                reservation_id
            )
            doc_ref.delete()
            
            self.logger.info("Successfully deleted booking",
                           reservation_id=reservation_id)
            return True
            
        except Exception as e:
            self.logger.error("Error deleting booking",
                            reservation_id=reservation_id,
                            error=str(e))
            return False
    
    def get_booking_stats(self) -> Dict[str, Any]:
        """
        Get booking statistics from Firestore.
        
        Returns:
            Dictionary with booking statistics
        """
        try:
            if not self.initialized:
                if not self.initialize():
                    return {}
            
            # Get total count
            total_docs = self.db.collection(app_config.bookings_collection).stream()
            total_count = len(list(total_docs))
            
            # Get counts by platform
            platform_stats = {}
            for platform in ['vrbo', 'airbnb', 'booking']:
                platform_docs = self.db.collection(app_config.bookings_collection).where(
                    'platform', '==', platform
                ).stream()
                platform_stats[platform] = len(list(platform_docs))
            
            stats = {
                'total_bookings': total_count,
                'by_platform': platform_stats
            }
            
            self.logger.info("Retrieved booking statistics", stats=stats)
            return stats
            
        except Exception as e:
            self.logger.error("Error getting booking statistics", error=str(e))
            return {}
    
    def _get_booking_by_reservation_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        """Internal method to get booking by reservation ID."""
        try:
            doc_ref = self.db.collection(app_config.bookings_collection).document(
                reservation_id
            )
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                return None
                
        except Exception as e:
            self.logger.error("Error getting booking by reservation ID",
                            reservation_id=reservation_id,
                            error=str(e))
            return None
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Firestore client doesn't need explicit cleanup
        pass
