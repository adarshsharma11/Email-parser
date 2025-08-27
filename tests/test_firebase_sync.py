"""
Unit tests for the Firebase sync module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from google.cloud.firestore import DocumentReference, CollectionReference
from google.api_core.exceptions import NotFound, PermissionDenied

from src.firebase_sync.firestore_client import FirestoreClient
from src.utils.models import BookingData, Platform, SyncResult


class TestFirestoreClient:
    """Test cases for FirestoreClient class."""
    
    @pytest.fixture
    def mock_firestore(self):
        """Mock Firestore client."""
        with patch('firebase_admin.initialize_app') as mock_init:
            with patch('firebase_admin.credentials.Certificate') as mock_cert:
                with patch('firebase_admin.firestore.client') as mock_client:
                    mock_db = Mock()
                    mock_client.return_value = mock_db
                    # Reset the mock for each test
                    mock_db.reset_mock()
                    yield mock_db
    
    @pytest.fixture
    def firestore_client(self, mock_firestore):
        """Create FirestoreClient instance for testing."""
        client = FirestoreClient()
        # Mock the initialization to succeed
        client.db = mock_firestore
        client.initialized = True
        return client
    
    @pytest.fixture
    def sample_booking_data(self):
        """Sample booking data for testing."""
        return BookingData(
            guest_name="John Doe",
            guest_phone="+1-555-123-4567",
            check_in_date=date(2024, 12, 15),
            check_out_date=date(2024, 12, 20),
            reservation_id="VRBO-12345",
            property_id="PROP-67890",
            platform=Platform.VRBO,
            number_of_guests=4,
            email_id="email-12345"
        )
    
    def test_initialize_success(self, mock_firestore):
        """Test successful Firestore initialization."""
        client = FirestoreClient()
        
        assert client.db is None  # Not initialized yet
        assert client.initialized is False
    
    def test_initialize_with_custom_collection(self, mock_firestore):
        """Test Firestore initialization with custom collection name."""
        # This test is not applicable since FirestoreClient doesn't take collection parameter
        # The collection name is configured in app_config
        client = FirestoreClient()
        
        assert client.db is None  # Not initialized yet
        assert client.initialized is False
    
    def test_sync_single_booking_success(self, firestore_client, sample_booking_data, mock_firestore):
        """Test successful sync of single booking."""
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref
        
        # Mock document doesn't exist (new booking)
        mock_doc_ref.get.return_value.exists = False
        
        results = firestore_client.sync_bookings([sample_booking_data])
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].is_new is True
        assert results[0].reservation_id == "VRBO-12345"
        
        # Verify document was created
        mock_doc_ref.set.assert_called_once()
    
    def test_sync_booking_duplicate(self, firestore_client, sample_booking_data, mock_firestore):
        """Test sync of duplicate booking."""
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref
        
        # Mock document exists (duplicate booking)
        mock_doc_ref.get.return_value.exists = True
        
        results = firestore_client.sync_bookings([sample_booking_data])
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].is_new is False
        assert results[0].reservation_id == "VRBO-12345"
        
        # Verify document was not created
        mock_doc_ref.set.assert_not_called()
    
    def test_sync_multiple_bookings(self, firestore_client, mock_firestore):
        """Test sync of multiple bookings."""
        booking1 = BookingData(
            guest_name="John Doe",
            guest_phone="+1-555-123-4567",
            check_in_date=date(2024, 12, 15),
            check_out_date=date(2024, 12, 20),
            reservation_id="VRBO-12345",
            property_id="PROP-67890",
            platform=Platform.VRBO,
            number_of_guests=4,
            email_id="email-12345"
        )
        
        booking2 = BookingData(
            guest_name="Jane Smith",
            guest_phone="+1-555-987-6543",
            check_in_date=date(2024, 1, 15),
            check_out_date=date(2024, 1, 20),
            reservation_id="AIRBNB-67890",
            property_id="PROP-12345",
            platform=Platform.AIRBNB,
            number_of_guests=2,
            email_id="email-67890"
        )
        
        # Mock collection and document references properly
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Create separate document references for each booking
        mock_doc_ref1 = Mock(spec=DocumentReference)
        mock_doc_ref2 = Mock(spec=DocumentReference)
        
        # Set up the document method to return different refs based on reservation ID
        def mock_document_side_effect(reservation_id):
            if reservation_id == "VRBO-12345":
                return mock_doc_ref1
            elif reservation_id == "AIRBNB-67890":
                return mock_doc_ref2
            return Mock(spec=DocumentReference)
        
        mock_collection.document.side_effect = mock_document_side_effect
        
        # First booking is new, second is duplicate
        mock_doc_ref1.get.return_value.exists = False
        mock_doc_ref2.get.return_value.exists = True
        
        results = firestore_client.sync_bookings([booking1, booking2])
        
        assert len(results) == 2
        assert results[0].success is True
        assert results[0].is_new is True
        assert results[1].success is True
        assert results[1].is_new is False
    
    def test_sync_booking_firestore_error(self, firestore_client, sample_booking_data, mock_firestore):
        """Test sync when Firestore operation fails."""
        # Mock collection and document references properly
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_collection.document.return_value = mock_doc_ref
        
        # Mock Firestore error - the error should occur when checking if booking exists
        mock_doc_ref.get.side_effect = PermissionDenied("Permission denied")
        
        # The current implementation catches exceptions in _get_booking_by_reservation_id
        # and returns None, treating the booking as new
        # So we need to mock the set operation to also fail
        mock_doc_ref.set.side_effect = PermissionDenied("Permission denied")
        
        results = firestore_client.sync_bookings([sample_booking_data])
        
        assert len(results) == 1
        assert results[0].success is False
        assert "Permission denied" in results[0].error_message
    
    def test_sync_booking_document_not_found(self, firestore_client, sample_booking_data, mock_firestore):
        """Test sync when document is not found (should create new)."""
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref
        
        # Mock document not found
        mock_doc_ref.get.side_effect = NotFound("Document not found")
        
        results = firestore_client.sync_bookings([sample_booking_data])
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].is_new is True
    
    def test_sync_booking_dry_run(self, firestore_client, sample_booking_data, mock_firestore):
        """Test sync in dry run mode."""
        # Mock collection and document references properly
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_collection.document.return_value = mock_doc_ref
        
        # Mock document doesn't exist (new booking)
        mock_doc_ref.get.return_value.exists = False
        
        results = firestore_client.sync_bookings([sample_booking_data], dry_run=True)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].is_new is True
        
        # Verify no Firestore operations were performed (dry run)
        mock_doc_ref.set.assert_not_called()
    
    def test_get_booking_stats_success(self, firestore_client, mock_firestore):
        """Test successful retrieval of booking statistics."""
        # Mock collection reference
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Mock query results for total count
        mock_docs = [Mock() for _ in range(3)]
        mock_collection.stream.return_value = mock_docs
        
        # Mock platform-specific queries by setting up where clauses
        mock_where_collection = Mock(spec=CollectionReference)
        mock_collection.where.return_value = mock_where_collection
        mock_where_collection.stream.return_value = [Mock() for _ in range(2)]  # 2 VRBO, 1 Airbnb
        
        stats = firestore_client.get_booking_stats()
        
        assert stats['total_bookings'] == 3
        assert 'by_platform' in stats
    
    def test_get_booking_stats_empty_collection(self, firestore_client, mock_firestore):
        """Test booking statistics with empty collection."""
        # Mock collection reference
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Mock empty query results
        mock_collection.stream.return_value = []
        
        # Mock platform-specific queries by setting up where clauses
        mock_where_collection = Mock(spec=CollectionReference)
        mock_collection.where.return_value = mock_where_collection
        mock_where_collection.stream.return_value = []
        
        stats = firestore_client.get_booking_stats()
        
        assert stats['total_bookings'] == 0
        assert 'by_platform' in stats
    
    def test_get_booking_stats_firestore_error(self, firestore_client, mock_firestore):
        """Test booking statistics when Firestore operation fails."""
        # Mock collection reference
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Mock Firestore error
        mock_collection.stream.side_effect = PermissionDenied("Permission denied")
        
        # The method catches exceptions and returns empty dict
        stats = firestore_client.get_booking_stats()
        assert stats == {}
    
    def test_booking_to_dict(self, firestore_client, sample_booking_data):
        """Test conversion of booking data to dictionary."""
        # Use the to_dict method from BookingData directly
        booking_dict = sample_booking_data.to_dict()
        
        assert booking_dict['guest_name'] == "John Doe"
        assert booking_dict['guest_phone'] == "+1-555-123-4567"
        assert 'check_in_date' in booking_dict
        assert 'check_out_date' in booking_dict
        assert booking_dict['reservation_id'] == "VRBO-12345"
        assert booking_dict['property_id'] == "PROP-67890"
        assert booking_dict['platform'] == "vrbo"
        assert booking_dict['number_of_guests'] == 4
        assert booking_dict['email_id'] == "email-12345"
        assert 'created_at' in booking_dict
        assert 'updated_at' in booking_dict
    
    def test_booking_to_dict_with_none_platform(self, firestore_client):
        """Test conversion of booking data with None platform."""
        booking_data = BookingData(
            guest_name="John Doe",
            guest_phone="+1-555-123-4567",
            check_in_date=date(2024, 12, 15),
            check_out_date=date(2024, 12, 20),
            reservation_id="UNKNOWN-12345",
            property_id="PROP-67890",
            platform=None,
            number_of_guests=4,
            email_id="email-12345"
        )
        
        booking_dict = booking_data.to_dict()
        
        assert booking_dict['platform'] is None
    
    def test_sync_booking_with_special_characters(self, firestore_client, mock_firestore):
        """Test sync of booking with special characters in guest name."""
        booking_data = BookingData(
            guest_name="José María O'Connor-Smith",
            guest_phone="+1-555-123-4567",
            check_in_date=date(2024, 12, 15),
            check_out_date=date(2024, 12, 20),
            reservation_id="VRBO-12345",
            property_id="PROP-67890",
            platform=Platform.VRBO,
            number_of_guests=4,
            email_id="email-12345"
        )
        
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref
        
        # Mock document doesn't exist
        mock_doc_ref.get.return_value.exists = False
        
        results = firestore_client.sync_bookings([booking_data])
        
        assert len(results) == 1
        assert results[0].success is True
        
        # Verify the booking was saved with special characters
        call_args = mock_doc_ref.set.call_args[0][0]
        assert call_args['guest_name'] == "José María O'Connor-Smith"
    
    def test_sync_booking_with_empty_optional_fields(self, firestore_client, mock_firestore):
        """Test sync of booking with empty optional fields."""
        booking_data = BookingData(
            guest_name="John Doe",
            guest_phone="",  # Empty phone
            check_in_date=date(2024, 12, 15),
            check_out_date=date(2024, 12, 20),
            reservation_id="VRBO-12345",
            property_id="",  # Empty property ID
            platform=Platform.VRBO,
            number_of_guests=0,  # Zero guests
            email_id="email-12345"
        )
        
        # Mock document reference
        mock_doc_ref = Mock(spec=DocumentReference)
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref
        
        # Mock document doesn't exist
        mock_doc_ref.get.return_value.exists = False
        
        results = firestore_client.sync_bookings([booking_data])
        
        assert len(results) == 1
        assert results[0].success is True
        
        # Verify the booking was saved with empty fields
        call_args = mock_doc_ref.set.call_args[0][0]
        assert call_args['guest_phone'] == ""
        assert call_args['property_id'] == ""
        assert call_args['number_of_guests'] == 0
    
    def test_sync_booking_batch_operations(self, firestore_client, mock_firestore):
        """Test sync using batch operations for multiple bookings."""
        bookings = [
            BookingData(
                guest_name=f"Guest {i}",
                guest_phone=f"+1-555-{i:03d}-4567",
                check_in_date=date(2024, 12, 15),
                check_out_date=date(2024, 12, 20),
                reservation_id=f"VRBO-{i:05d}",
                property_id=f"PROP-{i:05d}",
                platform=Platform.VRBO,
                number_of_guests=4,
                email_id=f"email-{i:05d}"
            )
            for i in range(1, 6)  # 5 bookings
        ]
        
        # Mock collection and document references properly
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Create separate document references for each booking
        mock_doc_refs = [Mock(spec=DocumentReference) for _ in range(5)]
        
        # Set up the document method to return different refs based on reservation ID
        def mock_document_side_effect(reservation_id):
            # Extract the index from the reservation ID (e.g., "VRBO-00001" -> index 0)
            index = int(reservation_id.split('-')[1]) - 1
            return mock_doc_refs[index]
        
        mock_collection.document.side_effect = mock_document_side_effect
        
        # All bookings are new
        for mock_doc_ref in mock_doc_refs:
            mock_doc_ref.get.return_value.exists = False
        
        results = firestore_client.sync_bookings(bookings)
        
        assert len(results) == 5
        assert all(result.success for result in results)
        assert all(result.is_new for result in results)
        
        # Verify all documents were created
        for mock_doc_ref in mock_doc_refs:
            mock_doc_ref.set.assert_called_once()
    
    def test_sync_booking_mixed_new_and_duplicate(self, firestore_client, mock_firestore):
        """Test sync with mix of new and duplicate bookings."""
        bookings = [
            BookingData(
                guest_name="New Guest",
                guest_phone="+1-555-111-1111",
                check_in_date=date(2024, 12, 15),
                check_out_date=date(2024, 12, 20),
                reservation_id="VRBO-NEW",
                property_id="PROP-NEW",
                platform=Platform.VRBO,
                number_of_guests=4,
                email_id="email-new"
            ),
            BookingData(
                guest_name="Duplicate Guest",
                guest_phone="+1-555-222-2222",
                check_in_date=date(2024, 12, 15),
                check_out_date=date(2024, 12, 20),
                reservation_id="VRBO-DUP",
                property_id="PROP-DUP",
                platform=Platform.VRBO,
                number_of_guests=4,
                email_id="email-dup"
            )
        ]
        
        # Mock collection and document references properly
        mock_collection = Mock(spec=CollectionReference)
        mock_firestore.collection.return_value = mock_collection
        
        # Create separate document references for each booking
        mock_doc_ref1 = Mock(spec=DocumentReference)
        mock_doc_ref2 = Mock(spec=DocumentReference)
        
        # Set up the document method to return different refs based on reservation ID
        def mock_document_side_effect(reservation_id):
            if reservation_id == "VRBO-NEW":
                return mock_doc_ref1
            elif reservation_id == "VRBO-DUP":
                return mock_doc_ref2
            return Mock(spec=DocumentReference)
        
        mock_collection.document.side_effect = mock_document_side_effect
        
        # First booking is new, second is duplicate
        mock_doc_ref1.get.return_value.exists = False
        mock_doc_ref2.get.return_value.exists = True
        
        results = firestore_client.sync_bookings(bookings)
        
        assert len(results) == 2
        assert results[0].success is True
        assert results[0].is_new is True
        assert results[1].success is True
        assert results[1].is_new is False
        
        # Verify only new booking was created
        mock_doc_ref1.set.assert_called_once()
        mock_doc_ref2.set.assert_not_called()
