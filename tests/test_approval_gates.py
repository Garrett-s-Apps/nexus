"""
Test User Approval Gates

Verifies that approval gate functions are properly structured and callable.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.orchestrator.approval import (
    request_architectural_decision_approval,
    request_budget_approval,
    request_spec_to_dev_approval,
    request_user_approval,
)


@pytest.mark.asyncio
async def test_request_user_approval_approved():
    """Test user approval when user approves."""
    with patch('src.orchestrator.approval._get_user_input', return_value='A'):
        result = await request_user_approval(
            "Test Approval",
            {
                "description": "Test description",
                "cost": "$10.00",
                "risk": "Low risk",
            },
            timeout_seconds=1,
        )
        assert result is True


@pytest.mark.asyncio
async def test_request_user_approval_rejected():
    """Test user approval when user rejects."""
    with patch('src.orchestrator.approval._get_user_input', return_value='R'):
        result = await request_user_approval(
            "Test Approval",
            {
                "description": "Test description",
                "cost": "$10.00",
                "risk": "Low risk",
            },
            timeout_seconds=1,
        )
        assert result is False


@pytest.mark.asyncio
async def test_request_budget_approval_below_threshold():
    """Test budget approval auto-approves below threshold."""
    result = await request_budget_approval(
        total_budget=30.0,
        breakdown={"planning": 10.0, "implementation": 20.0},
        threshold=50.0,
    )
    assert result is True


@pytest.mark.asyncio
async def test_request_budget_approval_above_threshold():
    """Test budget approval requires user input above threshold."""
    with patch('src.orchestrator.approval._get_user_input', return_value='A'):
        result = await request_budget_approval(
            total_budget=75.0,
            breakdown={"planning": 25.0, "implementation": 50.0},
            threshold=50.0,
        )
        assert result is True


@pytest.mark.asyncio
async def test_request_spec_to_dev_approval():
    """Test spec to dev transition approval."""
    with patch('src.orchestrator.approval._get_user_input', return_value='A'):
        result = await request_spec_to_dev_approval(
            spec_summary="Build a feature",
            estimated_cost=25.0,
            acceptance_criteria=["Criterion 1", "Criterion 2"],
        )
        assert result is True


@pytest.mark.asyncio
async def test_request_architectural_decision_approval():
    """Test architectural decision approval."""
    with patch('src.orchestrator.approval._get_user_input', return_value='A'):
        result = await request_architectural_decision_approval(
            decision_title="Use microservices",
            decision_details="Adopt microservices architecture",
            impact="Increases complexity but improves scalability",
            alternatives=["Monolith", "Modular monolith"],
        )
        assert result is True


@pytest.mark.asyncio
async def test_request_user_approval_timeout():
    """Test user approval timeout behavior."""
    async def slow_input(_func, _prompt):
        await asyncio.sleep(10)
        return 'A'

    with patch('src.orchestrator.approval.asyncio.to_thread', side_effect=slow_input):
        result = await request_user_approval(
            "Test Approval",
            {"description": "Test", "cost": "$10", "risk": "Low"},
            timeout_seconds=0.1,
        )
        assert result is False


@pytest.mark.asyncio
async def test_request_user_approval_invalid_input():
    """Test user approval with invalid input defaults to reject."""
    with patch('src.orchestrator.approval._get_user_input', return_value='X'):
        result = await request_user_approval(
            "Test Approval",
            {"description": "Test", "cost": "$10", "risk": "Low"},
            timeout_seconds=1,
        )
        assert result is False
