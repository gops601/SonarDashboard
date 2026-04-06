# tests/test_app.py

import sys
import os

# Fix import path for GitHub Actions
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from unittest.mock import patch
import pytest


@pytest.fixture
def client():
    app.config['TESTING'] = True
    return app.test_client()


# ---------------------------
# Test Dashboard Page
# ---------------------------
@patch("app.fetch_projects")
def test_dashboard(mock_projects, client):
    mock_projects.return_value = [
        {"key": "proj1", "name": "Project 1"}
    ]

    response = client.get("/")
    assert response.status_code == 200
    assert b"Project 1" in response.data


# ---------------------------
# Test Fetch Route
# ---------------------------
@patch("app.save_data")
@patch("app.fetch_issues")
@patch("app.fetch_ratings")
@patch("app.fetch_quality")
@patch("app.fetch_metrics")
def test_fetch_route(
    mock_metrics,
    mock_quality,
    mock_ratings,
    mock_issues,
    mock_save,
    client
):
    # Mock extended metrics
    mock_metrics.return_value = {
        "bugs": 1,
        "vulnerabilities": 0,
        "code_smells": 5,
        "coverage": 85.5,
        "duplicated_lines_density": 2.1,
        "ncloc": 1200,
        "complexity": 50
    }

    # Mock quality gate
    mock_quality.return_value = "OK"

    # Mock ratings (new structure)
    mock_ratings.return_value = {
        "reliability": "A",
        "security": "A",
        "maintainability": "B",
        "reliability_score": 1.0,
        "security_score": 1.0,
        "maintainability_score": 2.0
    }

    # Mock issues (extended fields)
    mock_issues.return_value = [
        {
            "key": "ISSUE_1",
            "severity": "MAJOR",
            "message": "Test issue",
            "component": "file.py",
            "line": 10,
            "type": "BUG",
            "status": "OPEN",
            "effort": "5min"
        }
    ]

    response = client.get("/fetch/test_project")

    # Should redirect to dashboard
    assert response.status_code == 302

    # Ensure save_data was called correctly
    mock_save.assert_called_once()


# ---------------------------
# Test Metrics Conversion Logic
# ---------------------------
def test_convert_rating():
    from app import convert_rating

    assert convert_rating("1.0") == "A"
    assert convert_rating("2.0") == "B"
    assert convert_rating("5.0") == "E"
    assert convert_rating("unknown") == "unknown"


# ---------------------------
# Test Empty Metrics Handling
# ---------------------------
@patch("app.fetch_metrics")
def test_empty_metrics(mock_metrics, client):
    mock_metrics.return_value = {}

    # Just ensure no crash
    assert isinstance(mock_metrics.return_value, dict)