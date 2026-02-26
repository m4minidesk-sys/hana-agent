"""Tests for yui.workshop.resource_manager (AC-80, AC-81)."""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError
from yui.workshop.resource_manager import ResourceManager, TAG_KEY, _parse_arn_service


def _client_error(code="AccessDenied", message="Denied"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "TestOp")


def _make_manager(max_cost_usd=10.0, tag_client=None, ce_cost=None):
    session = MagicMock()
    mock_tagging = tag_client or MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = []
    mock_tagging.get_paginator.return_value = mock_paginator
    mock_ce = MagicMock()
    if ce_cost is not None:
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": str(ce_cost), "Unit": "USD"}}}]
        }
    else:
        mock_ce.get_cost_and_usage.return_value = {"ResultsByTime": []}
    def _client_factory(service, region_name=None):
        if service == "resourcegroupstaggingapi":
            return mock_tagging
        if service == "ce":
            return mock_ce
        return MagicMock()
    session.client.side_effect = _client_factory
    mgr = ResourceManager(region="us-east-1", max_cost_usd=max_cost_usd, session=session)
    return mgr, session


class TestParseArnService:
    def test_ec2_instance(self):
        assert _parse_arn_service("arn:aws:ec2:us-east-1:123:instance/i-abc") == "ec2:instance"

    def test_s3_bucket(self):
        result = _parse_arn_service("arn:aws:s3:::my-bucket")
        assert result is None or result == "s3"

    def test_lambda_function(self):
        assert _parse_arn_service("arn:aws:lambda:us-east-1:123:function:my-fn") == "lambda"

    def test_iam_role(self):
        assert _parse_arn_service("arn:aws:iam::123:role/my-role") == "iam:role"

    def test_dynamodb_table(self):
        assert _parse_arn_service("arn:aws:dynamodb:us-east-1:123:table/my-table") == "dynamodb:table"

    def test_invalid_arn(self):
        assert _parse_arn_service("not-an-arn") is None

    def test_ec2_security_group(self):
        assert _parse_arn_service("arn:aws:ec2:us-east-1:123:security-group/sg-abc") == "ec2:security-group"


class TestTagResource:
    def test_tag_success(self):
        mgr, session = _make_manager()
        mgr.tag_resource("arn:aws:ec2:us-east-1:123:instance/i-abc", "wt-test1")
        mgr.tagging.tag_resources.assert_called_once_with(
            ResourceARNList=["arn:aws:ec2:us-east-1:123:instance/i-abc"],
            Tags={TAG_KEY: "wt-test1"},
        )

    def test_tag_client_error_propagates(self):
        mgr, _ = _make_manager()
        mgr.tagging.tag_resources.side_effect = _client_error()
        with pytest.raises(ClientError):
            mgr.tag_resource("arn:aws:ec2:us-east-1:123:instance/i-abc", "wt-test1")


class TestFindTestResources:
    def test_find_returns_arns(self):
        mgr, _ = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:ec2:us-east-1:123:instance/i-1"},
                {"ResourceARN": "arn:aws:ec2:us-east-1:123:instance/i-2"},
            ]}
        ]
        mgr.tagging.get_paginator.return_value = mock_paginator
        arns = mgr.find_test_resources("wt-test1")
        assert arns == [
            "arn:aws:ec2:us-east-1:123:instance/i-1",
            "arn:aws:ec2:us-east-1:123:instance/i-2",
        ]

    def test_find_empty(self):
        mgr, _ = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"ResourceTagMappingList": []}]
        mgr.tagging.get_paginator.return_value = mock_paginator
        arns = mgr.find_test_resources("wt-nonexistent")
        assert arns == []

    def test_find_multiple_pages(self):
        mgr, _ = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ResourceTagMappingList": [{"ResourceARN": "arn:aws:ec2:us-east-1:123:instance/i-1"}]},
            {"ResourceTagMappingList": [{"ResourceARN": "arn:aws:ec2:us-east-1:123:instance/i-2"}]},
        ]
        mgr.tagging.get_paginator.return_value = mock_paginator
        arns = mgr.find_test_resources("wt-test1")
        assert len(arns) == 2


class TestCleanupResources:
    def test_cleanup_ec2_instances(self):
        mgr, session = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:ec2:us-east-1:123:instance/i-abc123"},
            ]}
        ]
        mgr.tagging.get_paginator.return_value = mock_paginator
        result = mgr.cleanup_resources("wt-test1")
        assert "arn:aws:ec2:us-east-1:123:instance/i-abc123" in result["deleted"]
        assert len(result["failed"]) == 0

    def test_cleanup_skips_unknown_resource(self):
        mgr, _ = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:unknown:us-east-1:123:widget/w-1"},
            ]}
        ]
        mgr.tagging.get_paginator.return_value = mock_paginator
        result = mgr.cleanup_resources("wt-test1")
        assert "arn:aws:unknown:us-east-1:123:widget/w-1" in result["skipped"]

    def test_cleanup_handles_delete_error(self):
        mgr, session = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:ec2:us-east-1:123:instance/i-fail"},
            ]}
        ]
        mgr.tagging.get_paginator.return_value = mock_paginator
        mock_ec2 = MagicMock()
        mock_ec2.terminate_instances.side_effect = _client_error("InstanceNotFound")
        original_client = session.client.side_effect
        def _client_with_ec2_error(service, region_name=None):
            if service == "ec2":
                return mock_ec2
            return original_client(service, region_name=region_name)
        session.client.side_effect = _client_with_ec2_error
        result = mgr.cleanup_resources("wt-test1")
        assert "arn:aws:ec2:us-east-1:123:instance/i-fail" in result["failed"]

    def test_cleanup_no_resources(self):
        mgr, _ = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"ResourceTagMappingList": []}]
        mgr.tagging.get_paginator.return_value = mock_paginator
        result = mgr.cleanup_resources("wt-test1")
        assert result == {"deleted": [], "failed": [], "skipped": []}

    def test_cleanup_untags_deleted(self):
        mgr, session = _make_manager()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:lambda:us-east-1:123:function:my-fn"},
            ]}
        ]
        mgr.tagging.get_paginator.return_value = mock_paginator
        result = mgr.cleanup_resources("wt-test1")
        assert len(result["deleted"]) == 1
        mgr.tagging.untag_resources.assert_called_once_with(
            ResourceARNList=result["deleted"], TagKeys=[TAG_KEY],
        )


class TestCheckCostGuard:
    def test_within_limit(self):
        mgr, _ = _make_manager(max_cost_usd=10.0, ce_cost=5.0)
        assert mgr.check_cost_guard("wt-test1") is True

    def test_exceeds_limit(self):
        mgr, _ = _make_manager(max_cost_usd=10.0, ce_cost=15.0)
        assert mgr.check_cost_guard("wt-test1") is False

    def test_exactly_at_limit(self):
        mgr, _ = _make_manager(max_cost_usd=10.0, ce_cost=10.0)
        assert mgr.check_cost_guard("wt-test1") is True

    def test_ce_error_allows_continuation(self):
        mgr, session = _make_manager()
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.side_effect = _client_error("DataUnavailable")
        def _client_factory(service, region_name=None):
            if service == "ce":
                return mock_ce
            return MagicMock()
        session.client.side_effect = _client_factory
        mgr._session = session
        assert mgr.check_cost_guard("wt-test1") is True

    def test_zero_cost(self):
        mgr, _ = _make_manager(max_cost_usd=10.0, ce_cost=0.0)
        assert mgr.check_cost_guard("wt-test1") is True
