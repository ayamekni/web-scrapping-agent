from unittest.mock import patch

import pytest

from app.security import UnsafeUrlError, validate_public_url


@patch("app.security.socket.getaddrinfo")
def test_rejects_private_ip(mock_lookup):
    mock_lookup.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
    with pytest.raises(UnsafeUrlError):
        validate_public_url("http://example.test")


@patch("app.security.socket.getaddrinfo")
def test_accepts_public_ip(mock_lookup):
    mock_lookup.return_value = [(None, None, None, None, ("93.184.216.34", 443))]
    validate_public_url("https://example.com")

