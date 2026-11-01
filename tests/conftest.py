"""Pytest fixtures for CDE Lightband integration tests."""
import pytest

@pytest.fixture
def mock_credentials():
    return {
        "username": "testuser@example.com",
        "password": "CorrectPassword123!",
    }
