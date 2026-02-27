# Yui Agent Test Suite

> Test quality principles: goldbergyoni (R1-R28) + t-wada TDD (TW1-TW8)

## Test Classification

Tests are organized into 4 layers using pytest markers:

| Marker | Purpose | External Dependencies | CI Execution |
|---|---|---|---|
| `unit` | Pure logic, no I/O | None (all mocked) | Every PR |
| `component` | API-level integration | Mocked (boto3, slack_sdk, etc.) | Every PR |
| `integration` | Real AWS/Slack APIs | Real (requires credentials) | Every PR (with secrets) |
| `e2e` | Full end-to-end flows | Real (Slack → Bedrock → Slack) | Main branch only |

### Test Pyramid Distribution

```
    E2E (~10%)           Full flows, slow, fragile
   ─────────────
  Integration (~20%)    Real APIs, credentials required
 ───────────────────
Component (~50%)        Mocked APIs, fast, stable
─────────────────────
Unit (~20%)             Pure logic, no I/O
```

## Running Tests

```bash
# All unit + component tests (no credentials needed)
pytest tests/ -m 'not integration and not e2e' \
  --ignore=tests/test_meeting_manager.py \
  --ignore=tests/test_meeting_minutes.py \
  --ignore=tests/test_meeting_recorder.py \
  --ignore=tests/test_meeting_transcriber.py

# Integration tests (requires AWS + Slack credentials)
pytest tests/ -m integration

# E2E tests (requires full setup)
pytest tests/ -m e2e

# Specific test file
pytest tests/test_session.py -v

# With coverage
pytest tests/ -m 'not integration and not e2e' --cov=src/yui --cov-report=term-missing
```

## Fixture Inventory

### AWS / Bedrock Fixtures

| Fixture | Scope | Purpose | Usage Example |
|---|---|---|---|
| `mock_bedrock_client` | function | Stub for boto3 Bedrock client | `def test_foo(mock_bedrock_client): ...` |
| `mock_boto3_client` | function | Patches boto3.client globally | Auto-patches boto3.client calls |
| `mock_bedrock_model` | function | Stub for yui.agent.BedrockModel | Mocks model initialization |

### Slack Fixtures

| Fixture | Scope | Purpose | Usage Example |
|---|---|---|---|
| `mock_slack_client` | function | Stub for Slack WebClient | `def test_foo(mock_slack_client): ...` |

### Session / Storage Fixtures

| Fixture | Scope | Purpose | Usage Example |
|---|---|---|---|
| `session_manager` | function | In-memory SQLite session manager | `def test_foo(session_manager): ...` |
| `tmp_workspace` | function | Temporary workspace directory | `def test_foo(tmp_workspace): ...` |

### Faker Fixture

| Fixture | Scope | Purpose | Usage Example |
|---|---|---|---|
| `fake` | function | Faker instance for realistic test data (R6) | `fake.name()`, `fake.email()`, `fake.text()` |

**Important**: Each test gets its own seeded Faker instance (R15: no global seed). This ensures:
- **Reproducibility**: Same test → same seed → same data
- **Independence**: Different tests → different seeds → no data collision

## Test Quality Principles (TW1: 4 Properties)

Every test must satisfy these 4 properties:

### 1. Self-Validating

Tests pass or fail automatically without manual inspection.

```python
# ✅ Good: Clear assertion
def test_session_add_message__valid_message__increments_count(session_manager, fake):
    # Arrange
    session_id = fake.uuid4()
    session_manager.get_or_create_session(session_id)
    
    # Act
    session_manager.add_message(session_id, "user", fake.text())
    
    # Assert
    messages = session_manager.get_messages(session_id)
    assert len(messages) == 1

# ❌ Bad: Requires manual inspection
def test_session_add_message(session_manager):
    session_manager.add_message("test", "user", "hello")
    print(session_manager.get_messages("test"))  # Manual check needed
```

### 2. Repeatable

Tests produce the same result every time, regardless of environment or execution order.

```python
# ✅ Good: Uses faker with per-test seed
def test_bedrock_converse__normal_response__returns_text(mock_bedrock_client, fake):
    # Arrange
    user_message = fake.text()  # Seeded per test
    mock_bedrock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": fake.text()}]}}
    }
    
    # Act
    response = call_bedrock(user_message)
    
    # Assert
    assert response is not None

# ❌ Bad: Uses random data without seed
import random
def test_bedrock_converse(mock_bedrock_client):
    user_message = f"test_{random.randint(1, 1000)}"  # Non-repeatable
    # ...
```

### 3. Independent

Tests don't depend on each other or shared state. Can run in any order.

```python
# ✅ Good: Each test creates its own data
def test_session_get_messages__empty_session__returns_empty_list(session_manager, fake):
    session_id = fake.uuid4()
    session_manager.get_or_create_session(session_id)
    assert session_manager.get_messages(session_id) == []

def test_session_get_messages__with_messages__returns_list(session_manager, fake):
    session_id = fake.uuid4()
    session_manager.get_or_create_session(session_id)
    session_manager.add_message(session_id, "user", fake.text())
    assert len(session_manager.get_messages(session_id)) == 1

# ❌ Bad: Tests depend on execution order
session_id = "shared"  # Global state

def test_create_session(session_manager):
    session_manager.get_or_create_session(session_id)

def test_add_message(session_manager):
    # Assumes test_create_session ran first
    session_manager.add_message(session_id, "user", "hello")
```

### 4. Fast

Tests run quickly (<1s per test for unit/component, <5s for integration).

```python
# ✅ Good: Mocked I/O
def test_kiro_delegate__normal_command__returns_output(mock_subprocess, fake):
    mock_subprocess.run.return_value = MagicMock(stdout=fake.text(), returncode=0)
    result = kiro_delegate(fake.sentence())
    assert result is not None

# ❌ Bad: Real subprocess call
def test_kiro_delegate(fake):
    result = kiro_delegate(fake.sentence())  # Slow: real CLI execution
    assert result is not None
```

## TDD Cycle (TW4)

When adding new tests, follow this cycle:

### 1. TODO List

Write down test cases before coding:

```
TODO:
- [ ] test_session_add_message__valid_message__increments_count
- [ ] test_session_add_message__empty_text__raises_value_error
- [ ] test_session_add_message__nonexistent_session__creates_session
```

### 2. Red

Write a failing test first:

```python
def test_session_add_message__empty_text__raises_value_error(session_manager, fake):
    # Arrange
    session_id = fake.uuid4()
    session_manager.get_or_create_session(session_id)
    
    # Act & Assert
    with pytest.raises(ValueError, match="Message text cannot be empty"):
        session_manager.add_message(session_id, "user", "")
```

Run: `pytest tests/test_session.py::test_session_add_message__empty_text__raises_value_error`

Expected: **FAIL** (feature not implemented yet)

### 3. Green

Implement minimal code to make it pass:

```python
# src/yui/session.py
def add_message(self, session_id: str, role: str, text: str) -> None:
    if not text:
        raise ValueError("Message text cannot be empty")
    # ... rest of implementation
```

Run: `pytest tests/test_session.py::test_session_add_message__empty_text__raises_value_error`

Expected: **PASS**

### 4. Refactor

Clean up code while keeping tests green:

```python
# src/yui/session.py
def add_message(self, session_id: str, role: str, text: str) -> None:
    self._validate_message(text)  # Extract validation
    # ... rest of implementation

def _validate_message(self, text: str) -> None:
    if not text:
        raise ValueError("Message text cannot be empty")
```

Run: `pytest tests/test_session.py`

Expected: All tests **PASS**

## Test Naming Convention (R1: 3-Part Structure)

All new tests must follow this pattern:

```
test_<target>__<condition>__<expected_result>
```

Examples:

```python
# ✅ Good: Clear 3-part structure
def test_bedrock_converse__normal_response__returns_text(mock_bedrock_client, fake):
    ...

def test_bedrock_converse__timeout__raises_timeout_error(mock_bedrock_client):
    ...

def test_session_add_message__empty_text__raises_value_error(session_manager, fake):
    ...

# ❌ Bad: Unclear naming
def test_bedrock():
    ...

def test_session_message():
    ...
```

## AAA Pattern (R2: Arrange-Act-Assert)

Structure every test with blank lines separating the 3 sections:

```python
def test_session_add_message__valid_message__increments_count(session_manager, fake):
    # Arrange
    session_id = fake.uuid4()
    session_manager.get_or_create_session(session_id)
    message_text = fake.text()
    
    # Act
    session_manager.add_message(session_id, "user", message_text)
    
    # Assert
    messages = session_manager.get_messages(session_id)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == message_text
```

## Realistic Test Data (R6: Use Faker)

Always use faker for test data, never hardcoded strings like "foo", "bar", "test123".

```python
# ✅ Good: Realistic data with faker
def test_slack_post_message__normal_text__returns_ts(mock_slack_client, fake):
    # Arrange
    channel = fake.word()
    message = fake.sentence()
    mock_slack_client.chat_postMessage.return_value = {"ts": fake.uuid4()}
    
    # Act
    result = post_message(channel, message)
    
    # Assert
    assert result["ts"] is not None

# ❌ Bad: Hardcoded unrealistic data
def test_slack_post_message(mock_slack_client):
    result = post_message("test-channel", "foo bar")
    assert result["ts"] is not None
```

## Checklist for Adding New Tests

Before submitting a PR with new tests, verify:

- [ ] Test name follows 3-part structure: `test_<target>__<condition>__<expected>`
- [ ] Test uses AAA pattern with blank lines
- [ ] Test uses `fake` fixture for all test data (no "foo", "bar", "test123")
- [ ] Test is marked with appropriate marker (`@pytest.mark.unit`, `@pytest.mark.component`, etc.)
- [ ] External dependencies are mocked (boto3, slack_sdk, subprocess, etc.)
- [ ] Test satisfies TW1 properties: Self-Validating, Repeatable, Independent, Fast
- [ ] Test runs in <1s (unit/component) or <5s (integration)
- [ ] Test passes when run alone: `pytest tests/test_foo.py::test_bar -v`
- [ ] Test passes when run with full suite: `pytest tests/`

## Mock Quality Scripts

### Generate Mock Fixtures

```bash
# Generate stub fixtures for a new module
python scripts/generate_mock_fixtures.py src/yui/tools/new_tool.py

# Generate factory fixtures
python scripts/generate_mock_fixtures.py src/yui/tools/new_tool.py --factory
```

### Check Mock Coverage

```bash
# Check for unmocked external dependencies
python scripts/check_mock_coverage.py
```

### Check Unused Mocks

```bash
# Detect unused fixtures
python scripts/check_unused_mocks.py
```

### Check Mock Drift

```bash
# Compare mocks with real APIs (requires credentials)
python scripts/check_mock_drift.py --dry-run
```

## Contract Tests

Contract tests verify that our mocks match real API behavior. Located in `tests/contracts/`:

- `test_bedrock_contract.py` - Bedrock Converse API
- `test_slack_contract.py` - Slack Web API
- `test_boto3_contract.py` - boto3 CloudFormation

Run contract tests:

```bash
pytest tests/contracts/ -m integration -v
```

## Resources

- [goldbergyoni JavaScript Testing Best Practices](https://github.com/goldbergyoni/javascript-testing-best-practices)
- [t-wada TDD Principles](https://www.slideshare.net/t_wada/tdd-live-coding)
- [pytest documentation](https://docs.pytest.org/)
- [Faker documentation](https://faker.readthedocs.io/)
