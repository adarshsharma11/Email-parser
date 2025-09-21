import pytest

pytestmark = pytest.mark.skip("Firebase sync tests skipped after migration to Supabase. Use test_supabase_client.py")
