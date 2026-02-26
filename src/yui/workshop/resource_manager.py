"""Resource Manager — tag-based cleanup and cost guard (AC-80, AC-81).

Manages AWS resources created during workshop tests by tagging them
and providing automated cleanup. Includes a cost guard to abort tests
that exceed a configured spending limit.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAG_KEY = "yui:workshop-test"

_RESOURCE_DELETERS: dict[str, str] = {
    "ec2:instance": "ec2",
    "ec2:security-group": "ec2",
    "ec2:vpc": "ec2",
    "s3": "s3",
    "lambda": "lambda",
    "cloudformation": "cloudformation",
    "iam:role": "iam",
    "iam:policy": "iam",
    "dynamodb:table": "dynamodb",
    "sqs": "sqs",
    "sns": "sns",
}


def _parse_arn_service(arn: str) -> str | None:
    """Extract a normalised service:resource-type key from an ARN."""
    match = re.match(r"arn:[^:]+:([^:]+):[^:]*:[^:]*:([^:/]+)", arn)
    if not match:
        return None
    service = match.group(1)
    resource_type = match.group(2)
    if service == "ec2" and resource_type.startswith("instance"):
        return "ec2:instance"
    if service == "ec2" and resource_type.startswith("security-group"):
        return "ec2:security-group"
    if service == "ec2" and resource_type.startswith("vpc"):
        return "ec2:vpc"
    if service == "iam" and resource_type.startswith("role"):
        return "iam:role"
    if service == "iam" and resource_type.startswith("policy"):
        return "iam:policy"
    if service == "dynamodb" and resource_type.startswith("table"):
        return "dynamodb:table"
    return service


# ---------------------------------------------------------------------------
# ResourceManager
# ---------------------------------------------------------------------------


class ResourceManager:
    """Tag-based AWS resource tracking and cleanup for workshop tests."""

    TAG_KEY = TAG_KEY

    def __init__(
        self,
        region: str = "us-east-1",
        max_cost_usd: float = 10.0,
        session: Any | None = None,
    ) -> None:
        self.region = region
        self.max_cost_usd = max_cost_usd
        self._session = session or boto3.Session(region_name=region)
        self.tagging = self._session.client(
            "resourcegroupstaggingapi", region_name=region
        )

    def tag_resource(self, resource_arn: str, test_id: str) -> None:
        """Attach a workshop-test tag to an AWS resource."""
        try:
            self.tagging.tag_resources(
                ResourceARNList=[resource_arn],
                Tags={self.TAG_KEY: test_id},
            )
            logger.info("Tagged %s with %s=%s", resource_arn, self.TAG_KEY, test_id)
        except ClientError as e:
            logger.error("Failed to tag %s: %s", resource_arn, e)
            raise

    def find_test_resources(self, test_id: str) -> list[str]:
        """Find all resource ARNs tagged with the given test ID."""
        arns: list[str] = []
        paginator = self.tagging.get_paginator("get_resources")
        pages = paginator.paginate(
            TagFilters=[{"Key": self.TAG_KEY, "Values": [test_id]}],
        )
        for page in pages:
            for mapping in page.get("ResourceTagMappingList", []):
                arns.append(mapping["ResourceARN"])
        return arns

    def cleanup_resources(self, test_id: str) -> dict[str, Any]:
        """Delete all AWS resources tagged with the test ID."""
        arns = self.find_test_resources(test_id)
        result: dict[str, list[str]] = {
            "deleted": [],
            "failed": [],
            "skipped": [],
        }

        for arn in arns:
            svc_key = _parse_arn_service(arn)
            if svc_key is None or svc_key not in _RESOURCE_DELETERS:
                logger.warning("No deleter for ARN %s (service=%s), skipping", arn, svc_key)
                result["skipped"].append(arn)
                continue

            try:
                self._delete_resource(arn, svc_key)
                result["deleted"].append(arn)
                logger.info("Deleted %s", arn)
            except ClientError as e:
                logger.error("Failed to delete %s: %s", arn, e)
                result["failed"].append(arn)

        if result["deleted"]:
            try:
                self.tagging.untag_resources(
                    ResourceARNList=result["deleted"],
                    TagKeys=[self.TAG_KEY],
                )
            except ClientError:
                logger.warning("Failed to untag deleted resources")

        return result

    def _delete_resource(self, arn: str, svc_key: str) -> None:
        """Delete a single resource based on its ARN and service key."""
        if svc_key == "ec2:instance":
            ec2 = self._session.client("ec2", region_name=self.region)
            instance_id = arn.rsplit("/", 1)[-1]
            ec2.terminate_instances(InstanceIds=[instance_id])
        elif svc_key == "s3":
            s3 = self._session.client("s3", region_name=self.region)
            bucket_name = arn.rsplit(":::", 1)[-1]
            try:
                objects = s3.list_objects_v2(Bucket=bucket_name)
                for obj in objects.get("Contents", []):
                    s3.delete_object(Bucket=bucket_name, Key=obj["Key"])
            except ClientError:
                pass
            s3.delete_bucket(Bucket=bucket_name)
        elif svc_key == "lambda":
            lam = self._session.client("lambda", region_name=self.region)
            func_name = arn.rsplit(":", 1)[-1]
            lam.delete_function(FunctionName=func_name)
        elif svc_key == "cloudformation":
            cfn = self._session.client("cloudformation", region_name=self.region)
            stack_name = arn.rsplit("/", 1)[-1].split("/")[0]
            cfn.delete_stack(StackName=stack_name)
        elif svc_key == "dynamodb:table":
            ddb = self._session.client("dynamodb", region_name=self.region)
            table_name = arn.rsplit("/", 1)[-1]
            ddb.delete_table(TableName=table_name)
        elif svc_key == "sqs":
            sqs = self._session.client("sqs", region_name=self.region)
            parts = arn.split(":")
            queue_name = parts[-1]
            account_id = parts[4]
            queue_url = f"https://sqs.{self.region}.amazonaws.com/{account_id}/{queue_name}"
            sqs.delete_queue(QueueUrl=queue_url)
        elif svc_key == "sns":
            sns = self._session.client("sns", region_name=self.region)
            sns.delete_topic(TopicArn=arn)
        elif svc_key == "ec2:security-group":
            ec2 = self._session.client("ec2", region_name=self.region)
            sg_id = arn.rsplit("/", 1)[-1]
            ec2.delete_security_group(GroupId=sg_id)
        elif svc_key == "iam:role":
            iam = self._session.client("iam", region_name=self.region)
            role_name = arn.rsplit("/", 1)[-1]
            iam.delete_role(RoleName=role_name)
        elif svc_key == "iam:policy":
            iam = self._session.client("iam", region_name=self.region)
            iam.delete_policy(PolicyArn=arn)
        else:
            raise ClientError(
                {"Error": {"Code": "UnsupportedResource", "Message": f"No handler for {svc_key}"}},
                "DeleteResource",
            )

    def check_cost_guard(self, test_id: str) -> bool:
        """Check whether projected costs exceed the configured limit.

        Returns True if costs are within the limit, False if limit exceeded.
        """
        try:
            ce = self._session.client("ce", region_name="us-east-1")
            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=1)

            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": start.isoformat(),
                    "End": end.isoformat(),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                Filter={
                    "Tags": {
                        "Key": self.TAG_KEY,
                        "Values": [test_id],
                    },
                },
            )

            total_cost = 0.0
            for period in response.get("ResultsByTime", []):
                amount_str = period.get("Total", {}).get("UnblendedCost", {}).get("Amount", "0")
                total_cost += float(amount_str)

            logger.info(
                "Cost guard: test_id=%s cost=%.2f limit=%.2f",
                test_id, total_cost, self.max_cost_usd,
            )

            return total_cost <= self.max_cost_usd

        except ClientError as e:
            logger.warning("Cost Explorer query failed: %s — allowing test to continue", e)
            return True
        except Exception as e:
            logger.warning("Cost guard check error: %s — allowing test to continue", e)
            return True
