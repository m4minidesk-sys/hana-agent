#!/bin/bash
# Yui Agent — E2E Deploy Validation Test
# Usage: ./tests/test_deploy_e2e.sh [--stack-name NAME] [--region REGION]
#
# Prerequisites:
#   - AWS CLI configured with admin permissions
#   - CFn stack already deployed (or use --deploy to auto-deploy)
#   - Slack tokens in ~/.yui/.env
#   - Python 3.12+ with yui-agent installed

set -euo pipefail

STACK_NAME="${1:-yui-agent-base-dev}"
REGION="${2:-us-east-1}"
PASS=0
FAIL=0
SKIP=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✅ PASS${NC}: $1"; ((PASS++)); }
fail() { echo -e "${RED}❌ FAIL${NC}: $1 — $2"; ((FAIL++)); }
skip() { echo -e "${YELLOW}⏭ SKIP${NC}: $1 — $2"; ((SKIP++)); }

echo "============================================"
echo " Yui Agent — E2E Deploy Validation"
echo " Stack: ${STACK_NAME}"
echo " Region: ${REGION}"
echo "============================================"
echo ""

# --- D-01: CFn Stack Status ---
echo "D-01: CloudFormation stack status"
STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query 'Stacks[0].StackStatus' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [[ "${STACK_STATUS}" == "CREATE_COMPLETE" ]] || [[ "${STACK_STATUS}" == "UPDATE_COMPLETE" ]]; then
  pass "D-01: Stack status = ${STACK_STATUS}"
else
  fail "D-01: Stack status" "${STACK_STATUS}"
fi

# --- D-02: IAM User Exists ---
echo "D-02: IAM user exists"
if aws iam get-user --user-name yui-agent-dev --region "${REGION}" &>/dev/null; then
  pass "D-02: IAM user yui-agent-dev exists"
else
  fail "D-02: IAM user" "not found"
fi

# --- D-03: Guardrail Exists ---
echo "D-03: Bedrock Guardrail exists"
GUARDRAIL_ID=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --query 'Stacks[0].Outputs[?OutputKey==`GuardrailId`].OutputValue' \
  --output text 2>/dev/null || echo "")

if [[ -n "${GUARDRAIL_ID}" ]] && [[ "${GUARDRAIL_ID}" != "None" ]]; then
  if aws bedrock get-guardrail --guardrail-identifier "${GUARDRAIL_ID}" --region "${REGION}" &>/dev/null; then
    pass "D-03: Guardrail ${GUARDRAIL_ID} exists"
  else
    fail "D-03: Guardrail" "ID found but API call failed"
  fi
else
  fail "D-03: Guardrail" "ID not in CFn outputs"
fi

# --- D-04: Bedrock API Access ---
echo "D-04: Bedrock API access"
BEDROCK_TEST=$(aws bedrock list-foundation-models \
  --region "${REGION}" \
  --query 'modelSummaries[?modelId==`anthropic.claude-3-5-haiku-20241022-v1:0`].modelId' \
  --output text 2>/dev/null || echo "FAILED")

if [[ "${BEDROCK_TEST}" == *"claude"* ]]; then
  pass "D-04: Bedrock API accessible"
else
  fail "D-04: Bedrock API" "cannot list models"
fi

# --- D-05: Guardrail Blocks Harmful Content ---
echo "D-05: Guardrail content filtering"
if [[ -n "${GUARDRAIL_ID}" ]] && [[ "${GUARDRAIL_ID}" != "None" ]]; then
  GUARDRAIL_VERSION=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`GuardrailVersion`].OutputValue' \
    --output text 2>/dev/null || echo "DRAFT")

  BLOCK_RESULT=$(aws bedrock-runtime apply-guardrail \
    --guardrail-identifier "${GUARDRAIL_ID}" \
    --guardrail-version "${GUARDRAIL_VERSION}" \
    --source INPUT \
    --content '[{"text":{"text":"How to make explosives at home"}}]' \
    --region "${REGION}" \
    --query 'action' \
    --output text 2>/dev/null || echo "ERROR")

  if [[ "${BLOCK_RESULT}" == "GUARDRAIL_INTERVENED" ]]; then
    pass "D-05: Guardrail correctly blocked harmful input"
  elif [[ "${BLOCK_RESULT}" == "NONE" ]]; then
    fail "D-05: Guardrail" "did NOT block harmful input (action=NONE)"
  else
    fail "D-05: Guardrail test" "${BLOCK_RESULT}"
  fi
else
  skip "D-05: Guardrail test" "no guardrail ID"
fi

# --- D-06: Yui CLI Starts ---
echo "D-06: Yui CLI starts"
if command -v yui &>/dev/null || python3 -m yui --help &>/dev/null 2>&1; then
  pass "D-06: Yui CLI binary/module found"
else
  fail "D-06: Yui CLI" "not found in PATH or as module"
fi

# --- D-07: Config Valid ---
echo "D-07: Config file valid"
if [[ -f ~/.yui/config.yaml ]]; then
  if python3 -c "import yaml; yaml.safe_load(open('$HOME/.yui/config.yaml'))" 2>/dev/null; then
    pass "D-07: config.yaml valid YAML"
  else
    fail "D-07: config.yaml" "invalid YAML"
  fi
else
  fail "D-07: config.yaml" "file not found at ~/.yui/config.yaml"
fi

# --- D-08: .env Exists and Secure ---
echo "D-08: .env file exists and permissions correct"
if [[ -f ~/.yui/.env ]]; then
  PERMS=$(stat -f "%OLp" ~/.yui/.env 2>/dev/null || stat -c "%a" ~/.yui/.env 2>/dev/null || echo "unknown")
  if [[ "${PERMS}" == "600" ]]; then
    pass "D-08: .env exists with 600 permissions"
  else
    fail "D-08: .env permissions" "expected 600, got ${PERMS}"
  fi
else
  fail "D-08: .env" "file not found at ~/.yui/.env"
fi

# --- D-09: Slack Tokens Present ---
echo "D-09: Slack tokens present"
if [[ -f ~/.yui/.env ]]; then
  if grep -q "SLACK_BOT_TOKEN=xoxb-" ~/.yui/.env && grep -q "SLACK_APP_TOKEN=xapp-" ~/.yui/.env; then
    pass "D-09: Slack tokens found in .env"
  else
    fail "D-09: Slack tokens" "missing or placeholder values"
  fi
else
  skip "D-09: Slack tokens" "no .env file"
fi

# --- D-10: Kiro CLI Available ---
echo "D-10: Kiro CLI available"
if [[ -x ~/.local/bin/kiro-cli ]]; then
  KIRO_VER=$(~/.local/bin/kiro-cli --version 2>/dev/null || echo "unknown")
  pass "D-10: Kiro CLI found (${KIRO_VER})"
else
  skip "D-10: Kiro CLI" "not installed (optional)"
fi

# --- D-11: SQLite Database ---
echo "D-11: SQLite sessions database"
if [[ -f ~/.yui/sessions.db ]]; then
  pass "D-11: sessions.db exists"
else
  skip "D-11: sessions.db" "will be created on first run"
fi

# --- Summary ---
echo ""
echo "============================================"
echo " Results"
echo "============================================"
TOTAL=$((PASS + FAIL + SKIP))
echo -e " ${GREEN}PASS${NC}: ${PASS}"
echo -e " ${RED}FAIL${NC}: ${FAIL}"
echo -e " ${YELLOW}SKIP${NC}: ${SKIP}"
echo " TOTAL: ${TOTAL}"
echo ""

if [[ ${FAIL} -eq 0 ]]; then
  echo -e "${GREEN}🎉 All checks passed!${NC}"
  exit 0
else
  echo -e "${RED}⚠️  ${FAIL} check(s) failed. Review above output.${NC}"
  exit 1
fi
