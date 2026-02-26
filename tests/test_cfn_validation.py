"""
CloudFormation テンプレートバリデーションテスト

Tests for yui-agent-base.yaml:
- YAML構文チェック
- テンプレート構造検証
- パラメータバリデーション
- リソース定義確認
- 出力値確認
- AWS実テスト（条件付き）
"""

import os
import pytest
import yaml
from pathlib import Path
import boto3


# CFn専用YAMLローダー（CFnタグを処理）
class CFnYAMLLoader(yaml.SafeLoader):
    pass

def cfn_constructor(loader, tag_suffix, node):
    """CFn intrinsic functionsを辞書として処理"""
    if isinstance(node, yaml.ScalarNode):
        return {f"!{tag_suffix}": loader.construct_scalar(node)}
    elif isinstance(node, yaml.SequenceNode):
        return {f"!{tag_suffix}": loader.construct_sequence(node)}
    elif isinstance(node, yaml.MappingNode):
        return {f"!{tag_suffix}": loader.construct_mapping(node)}
    else:
        return {f"!{tag_suffix}": None}

# CFnタグをローダーに登録
cfn_tags = ['Ref', 'GetAtt', 'Sub', 'Join', 'If', 'Not', 'Equals', 'GetAZs', 'Select', 'Split', 'Base64', 'Cidr']
for tag in cfn_tags:
    CFnYAMLLoader.add_multi_constructor(f'!{tag}', cfn_constructor)

# テンプレートファイルパス
CFN_TEMPLATE_PATH = Path(__file__).parent.parent / "cfn" / "yui-agent-base.yaml"


@pytest.fixture
def cfn_template():
    """CFnテンプレートのロード（CFn固有タグを処理）"""
    with open(CFN_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return yaml.load(f, CFnYAMLLoader)


@pytest.fixture
def cfn_template_str():
    """CFnテンプレートの文字列版"""
    with open(CFN_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestCFnTemplateStructure:
    """テンプレート構造の基本検証"""

    def test_yaml_parseable(self, cfn_template):
        """YAMLが正常にパース可能であることを確認"""
        assert cfn_template is not None
        assert isinstance(cfn_template, dict)

    def test_required_fields_present(self, cfn_template):
        """必須フィールドの存在確認"""
        required_fields = [
            "AWSTemplateFormatVersion",
            "Description",
            "Parameters", 
            "Resources",
            "Outputs"
        ]
        
        for field in required_fields:
            assert field in cfn_template, f"Required field '{field}' is missing"

    def test_aws_template_format_version(self, cfn_template):
        """AWSTemplateFormatVersionが正しいことを確認"""
        assert cfn_template["AWSTemplateFormatVersion"] == "2010-09-09"


class TestParameters:
    """パラメータ定義のバリデーション"""

    def test_parameter_definitions(self, cfn_template):
        """パラメータが正しく定義されていることを確認"""
        parameters = cfn_template["Parameters"]
        
        # 期待するパラメータ
        expected_params = ["Environment", "BedrockRegion", "GuardrailName", "ContentFilterStrength"]
        
        for param in expected_params:
            assert param in parameters, f"Parameter '{param}' is missing"

    def test_environment_parameter_validation(self, cfn_template):
        """Environmentパラメータの検証"""
        env_param = cfn_template["Parameters"]["Environment"]
        
        assert env_param["Type"] == "String"
        assert env_param["Default"] == "dev"
        assert set(env_param["AllowedValues"]) == {"dev", "staging", "prod"}

    def test_content_filter_strength_parameter(self, cfn_template):
        """ContentFilterStrengthパラメータの検証"""
        filter_param = cfn_template["Parameters"]["ContentFilterStrength"]
        
        assert filter_param["Type"] == "String"
        assert filter_param["Default"] == "HIGH"
        assert set(filter_param["AllowedValues"]) == {"NONE", "LOW", "MEDIUM", "HIGH"}


class TestResourceDefinitions:
    """リソース定義の確認"""

    def test_iam_resources_present(self, cfn_template):
        """IAM関連リソースの存在確認"""
        resources = cfn_template["Resources"]
        
        iam_resources = ["YuiPolicy", "YuiUser", "YuiAccessKey"]
        for resource in iam_resources:
            assert resource in resources, f"IAM resource '{resource}' is missing"

    def test_iam_resource_types(self, cfn_template):
        """IAMリソースタイプの検証"""
        resources = cfn_template["Resources"]
        
        assert resources["YuiPolicy"]["Type"] == "AWS::IAM::ManagedPolicy"
        assert resources["YuiUser"]["Type"] == "AWS::IAM::User"  
        assert resources["YuiAccessKey"]["Type"] == "AWS::IAM::AccessKey"

    def test_bedrock_guardrail_present(self, cfn_template):
        """Bedrock Guardrailリソースの存在確認"""
        resources = cfn_template["Resources"]
        
        assert "YuiGuardrail" in resources, "Bedrock Guardrail resource is missing"
        
        guardrail = resources["YuiGuardrail"]
        assert guardrail["Type"] == "AWS::Bedrock::Guardrail"

    def test_secrets_manager_present(self, cfn_template):
        """Secrets Managerリソースの存在確認"""
        resources = cfn_template["Resources"]
        
        assert "YuiSlackSecrets" in resources, "Secrets Manager resource is missing"
        
        secret = resources["YuiSlackSecrets"]
        assert secret["Type"] == "AWS::SecretsManager::Secret"


class TestOutputs:
    """出力値の検証"""

    def test_required_outputs_present(self, cfn_template):
        """必要な出力値が定義されていることを確認"""
        outputs = cfn_template["Outputs"]
        
        expected_outputs = [
            "YuiUserArn",
            "YuiAccessKeyId", 
            "YuiSecretAccessKey",
            "GuardrailId",
            "GuardrailVersion",
            "SlackSecretsArn",
            "PolicyArn"
        ]
        
        for output in expected_outputs:
            assert output in outputs, f"Output '{output}' is missing"

    def test_outputs_have_descriptions(self, cfn_template):
        """全ての出力値に説明があることを確認"""
        outputs = cfn_template["Outputs"]
        
        for output_name, output_def in outputs.items():
            assert "Description" in output_def, f"Output '{output_name}' lacks description"
            assert len(output_def["Description"]) > 0, f"Output '{output_name}' has empty description"


class TestTemplateValidation:
    """CFnテンプレート全体のバリデーション"""

    def test_template_has_all_required_resource_types(self, cfn_template):
        """必要なリソースタイプが全て含まれていることを確認"""
        resources = cfn_template["Resources"]
        resource_types = {res["Type"] for res in resources.values()}
        
        expected_types = {
            "AWS::IAM::ManagedPolicy",
            "AWS::IAM::User",
            "AWS::IAM::AccessKey", 
            "AWS::Bedrock::Guardrail",
            "AWS::SecretsManager::Secret"
        }
        
        assert expected_types.issubset(resource_types), f"Missing resource types: {expected_types - resource_types}"

    def test_bedrock_permissions_in_policy(self, cfn_template):
        """IAMポリシーにBedrock権限が含まれていることを確認"""
        policy = cfn_template["Resources"]["YuiPolicy"]
        policy_doc = policy["Properties"]["PolicyDocument"]
        statements = policy_doc["Statement"]
        
        # Bedrock関連のアクションを探す
        bedrock_actions = []
        for statement in statements:
            if isinstance(statement.get("Action"), list):
                bedrock_actions.extend([action for action in statement["Action"] if action.startswith("bedrock")])
        
        assert len(bedrock_actions) > 0, "No Bedrock permissions found in IAM policy"
        
        # 必須のBedrock権限を確認
        required_actions = {
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream",
            "bedrock:ApplyGuardrail",
            "bedrock:GetGuardrail"
        }
        actual_actions = set(bedrock_actions)
        assert required_actions.issubset(actual_actions), f"Missing Bedrock actions: {required_actions - actual_actions}"

    def test_agentcore_permissions_in_policy(self, cfn_template):
        """IAMポリシーにAgentCore権限が含まれていることを確認"""
        policy = cfn_template["Resources"]["YuiPolicy"]
        policy_doc = policy["Properties"]["PolicyDocument"]
        statements = policy_doc["Statement"]
        
        # AgentCore関連のアクションを探す
        agentcore_actions = []
        for statement in statements:
            if isinstance(statement.get("Action"), list):
                agentcore_actions.extend([action for action in statement["Action"] if action.startswith("bedrock-agentcore")])
        
        assert len(agentcore_actions) > 0, "No AgentCore permissions found in IAM policy"
        
        # 必須のAgentCore権限カテゴリを確認
        required_prefixes = [
            "bedrock-agentcore:CreateBrowserSession",
            "bedrock-agentcore:CreateMemory",
            "bedrock-agentcore:CreateCodeInterpreterSession"
        ]
        
        for prefix in required_prefixes:
            assert any(action.startswith(prefix) for action in agentcore_actions), f"Missing AgentCore permission: {prefix}"

    def test_guardrail_content_filters(self, cfn_template):
        """Guardrailにコンテンツフィルターが設定されていることを確認"""
        guardrail = cfn_template["Resources"]["YuiGuardrail"] 
        content_policy = guardrail["Properties"]["ContentPolicyConfig"]
        filters = content_policy["FiltersConfig"]
        
        # 期待するフィルタータイプ
        expected_filter_types = {"SEXUAL", "HATE", "VIOLENCE", "INSULTS", "MISCONDUCT", "PROMPT_ATTACK"}
        actual_filter_types = {f["Type"] for f in filters}
        
        assert expected_filter_types.issubset(actual_filter_types), f"Missing filter types: {expected_filter_types - actual_filter_types}"


# 実AWS環境でのテスト（skip条件付き）
class TestAWSIntegration:
    """実AWS環境での統合テスト"""
    
    @pytest.mark.aws
    @pytest.mark.skipif(
        not os.getenv("AWS_PROFILE") or os.getenv("SKIP_AWS_TESTS"), 
        reason="AWS credentials not available or SKIP_AWS_TESTS set"
    )
    def test_validate_template_real_aws(self, cfn_template_str):
        """実AWS環境でのvalidate-template実行"""
        client = boto3.client("cloudformation", region_name="us-east-1")
        
        try:
            response = client.validate_template(TemplateBody=cfn_template_str)
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
            
            # パラメータが正しく検出されることを確認
            param_names = {p["ParameterKey"] for p in response["Parameters"]}
            expected_params = {"Environment", "BedrockRegion", "GuardrailName", "ContentFilterStrength"}
            assert param_names >= expected_params
            
        except Exception as e:
            pytest.fail(f"AWS validate-template failed: {e}")

    @pytest.mark.aws
    @pytest.mark.skipif(
        not os.getenv("AWS_PROFILE") or os.getenv("SKIP_AWS_TESTS"),
        reason="AWS credentials not available or SKIP_AWS_TESTS set"
    )
    def test_create_changeset_dry_run(self, cfn_template_str):
        """dry-run changesetテスト"""
        client = boto3.client("cloudformation", region_name="us-east-1")
        
        stack_name = "yui-agent-test-stack-dry-run"
        changeset_name = "test-changeset"
        
        try:
            # changeset作成（実行はしない）
            response = client.create_change_set(
                StackName=stack_name,
                TemplateBody=cfn_template_str,
                ChangeSetName=changeset_name,
                Parameters=[
                    {"ParameterKey": "Environment", "ParameterValue": "dev"},
                    {"ParameterKey": "BedrockRegion", "ParameterValue": "us-east-1"},
                    {"ParameterKey": "GuardrailName", "ParameterValue": "test-guardrail"},
                    {"ParameterKey": "ContentFilterStrength", "ParameterValue": "MEDIUM"}
                ],
                Capabilities=["CAPABILITY_NAMED_IAM"]
            )
            
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
            assert response["Id"]  # changeset IDが取得できることを確認
            
        finally:
            # cleanup: changeset削除
            try:
                client.delete_change_set(
                    StackName=stack_name,
                    ChangeSetName=changeset_name
                )
            except Exception:
                pass  # cleanup失敗は無視