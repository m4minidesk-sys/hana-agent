# Issue #54: Bedrock Converse API Error Handling Requirements

## Overview
Implement comprehensive error handling for Bedrock Converse API in `src/yui/agent.py` to handle various AWS Bedrock exceptions with retry logic, fallback mechanisms, and user-friendly error messages.

## Current State Analysis

### Existing Code
- `src/yui/agent.py` uses `BedrockModel` from strands library
- Basic model creation with GuardRails support
- No specific Converse API error handling implemented
- No retry logic or exponential backoff

### Test Coverage
- New test file: `tests/test_converse_errors.py` (20+ test cases)
- Covers all major error scenarios with mocks and E2E tests
- Tests currently in RED state (failing as expected)

## Requirements

### AC-27: Permission Denied → Actionable IAM Error
**WHEN** Bedrock returns `AccessDeniedException`  
**THEN** Provide specific IAM policy guidance

**Implementation Details:**
- Catch `botocore.exceptions.ClientError` with `Error.Code == "AccessDeniedException"`
- Parse error message to identify missing permissions (e.g., `bedrock:InvokeModel`)
- Suggest specific IAM policy statements
- Include model-specific resource ARN in guidance when available

**Error Message Format:**
```
AWS IAM permission denied. Missing permission: bedrock:InvokeModel
Suggested IAM policy:
{
  "Version": "2012-10-17", 
  "Statement": [{
    "Effect": "Allow",
    "Action": "bedrock:InvokeModel", 
    "Resource": "arn:aws:bedrock:*:*:foundation-model/anthropic.claude-*"
  }]
}
```

### AC-28: Timeout → 3 Retries  
**WHEN** Bedrock operations timeout  
**THEN** Retry up to 3 times with exponential backoff

**Implementation Details:**
- Catch `botocore.exceptions.ReadTimeoutError`
- Implement exponential backoff: 1s, 2s, 4s delays
- Max 3 retries before final failure
- Log each retry attempt
- After 3 failed retries, provide clear timeout guidance

### Throttling Exception Handling
**WHEN** Bedrock returns `ThrottlingException`  
**THEN** Retry with exponential backoff (max 3 retries)

**Implementation Details:**
- Catch `ClientError` with `Error.Code == "ThrottlingException"`
- Use same exponential backoff as timeout (1s, 2s, 4s)
- Log throttling events for debugging
- Suggest rate limiting best practices in final error

### Model Not Found Error
**WHEN** Bedrock returns `ResourceNotFoundException`  
**THEN** Provide useful error message with model suggestions

**Implementation Details:**
- Catch `ClientError` with `Error.Code == "ResourceNotFoundException"`
- Extract requested model ID from error message
- Suggest alternative available models
- Include region-specific guidance

**Error Message Format:**
```
Model not found: anthropic.claude-3-nonexistent-v1:0
Available models in us-east-1:
- anthropic.claude-3-sonnet-20240229-v1:0
- anthropic.claude-3-haiku-20240307-v1:0
Check AWS console for model availability in your region.
```

### Validation Exception Handling
**WHEN** Bedrock returns `ValidationException`  
**THEN** Provide clear validation error with actionable guidance

**Implementation Details:**
- Parse validation error messages
- Identify common issues:
  - Token limits exceeded
  - Invalid parameters (max_tokens, temperature)
  - GuardRail configuration issues
- Provide specific remediation steps

### Service Unavailable Exception
**WHEN** Bedrock returns `ServiceUnavailableException`  
**THEN** Retry with backoff (max 3 retries)

**Implementation Details:**
- Same retry logic as throttling/timeout
- Log service outage events
- Provide AWS status page link in final error

### Token Limit Exceeded
**WHEN** Input exceeds model token limits  
**THEN** Provide clear error with chunking suggestions

**Implementation Details:**
- Detect token limit validation errors
- Calculate approximate input size
- Suggest input chunking strategies
- Include model-specific token limits

### ConverseStream Fallback
**WHEN** ConverseStream fails  
**THEN** Gracefully fallback to Converse

**Implementation Details:**
- Catch ConverseStream-specific errors
- Automatic fallback to non-streaming Converse API
- Log fallback events
- Maintain same functionality without streaming

## Implementation Architecture

### Error Handler Class Structure
Create `BedrockErrorHandler` class in `src/yui/agent.py`:

```python
class BedrockErrorHandler:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def handle_bedrock_error(self, error: Exception, operation: str) -> Any:
        """Main error handling dispatch method"""
        
    def _retry_with_backoff(self, func, *args, **kwargs) -> Any:
        """Exponential backoff retry logic"""
        
    def _format_access_denied_error(self, error: ClientError) -> str:
        """Format IAM guidance for access denied"""
        
    def _format_model_not_found_error(self, error: ClientError) -> str:
        """Format model availability guidance"""
        
    def _should_retry(self, error: Exception) -> bool:
        """Determine if error is retryable"""
```

### Integration Points
1. **Model Creation**: Wrap `BedrockModel` instantiation with error handling
2. **Conversation Calls**: Wrap actual model invocation calls  
3. **Streaming**: Add ConverseStream → Converse fallback logic
4. **Logging**: Add structured logging for all error events

### Configuration
Add error handling config section:
```yaml
model:
  error_handling:
    max_retries: 3
    backoff_base: 1.0  # seconds
    enable_fallback: true
    log_errors: true
```

## File Changes Required

### Primary Changes
- **`src/yui/agent.py`**: Add `BedrockErrorHandler` class and integrate with `create_agent()`

### Supporting Changes  
- **`yui/config.py`**: Add error_handling config schema if needed
- **Requirements**: No new dependencies required (using existing botocore)

## Testing Strategy

### Test Files
- **`tests/test_converse_errors.py`**: Already created with 20+ test cases
- **Existing tests**: Should continue passing

### Test Execution
```bash
# Unit tests (with mocks)
python -m pytest tests/test_converse_errors.py -v

# E2E tests (requires AWS credentials)  
python -m pytest tests/test_converse_errors.py::TestConverseE2E -v --aws

# All error handling tests
python -m pytest tests/test_error_handling.py tests/test_converse_errors.py -v
```

## Success Criteria

### Functional Requirements
✅ All 20+ tests in `test_converse_errors.py` pass  
✅ Existing tests continue to pass  
✅ Error messages are user-friendly and actionable  
✅ Retry logic works with exponential backoff  
✅ ConverseStream fallback works seamlessly  

### Non-Functional Requirements  
✅ Performance: Retry delays don't exceed 7s total (1+2+4)  
✅ Logging: All error events are properly logged  
✅ Maintainability: Clean separation of concerns  
✅ Documentation: Clear error message formats  

## Implementation Constraints

### Must Follow
- **Existing API**: Don't break current `create_agent()` signature
- **Configuration**: Use existing config structure where possible  
- **Dependencies**: No new external dependencies
- **Logging**: Use existing Python logging framework
- **Code Style**: Follow existing codebase patterns

### Must Avoid
- **Breaking Changes**: Existing agent functionality must work unchanged
- **Performance Impact**: Minimal overhead when no errors occur
- **Hard-Coded Values**: Use configuration for timeouts/retries
- **Silent Failures**: All errors should be logged

## Testing Notes

### Mock Strategy
- Mock `BedrockModel` class and instances
- Mock specific `converse()` and `converse_stream()` methods  
- Use `ClientError` from `botocore.exceptions` for realistic errors
- Test both single errors and retry scenarios

### E2E Strategy
- Use `@pytest.mark.aws` for tests requiring real AWS calls
- Skip AWS tests when credentials unavailable
- Use small/cheap models for E2E tests (claude-3-haiku)
- Test with intentionally invalid configurations

## Implementation Priority

1. **Core Error Handler**: `BedrockErrorHandler` class with basic retry logic
2. **Access Denied**: IAM guidance formatting (AC-27)  
3. **Timeout Retries**: 3-retry logic with backoff (AC-28)
4. **Throttling**: Rate limiting retry logic
5. **Model Not Found**: Model suggestion logic
6. **Validation Errors**: Parameter validation guidance
7. **Stream Fallback**: ConverseStream → Converse fallback
8. **Service Unavailable**: Transient error retry
9. **Token Limits**: Input chunking suggestions
10. **Integration**: Wire handler into `create_agent()`

## Acceptance Testing

After implementation, verify:
```bash
# 1. All new tests pass
python -m pytest tests/test_converse_errors.py -x -q

# 2. Existing tests still pass  
python -m pytest tests/test_error_handling.py -x -q

# 3. Integration tests pass
python -m pytest tests/test_integration.py -x -q  

# 4. Real AWS error handling (optional)
python -m pytest tests/test_converse_errors.py::TestConverseE2E -v
```

## Related Files to Review
- `tests/test_error_handling.py` - Existing error handling tests
- `src/yui/config.py` - Configuration loading
- `tests/test_integration.py` - Integration test patterns
- `src/yui/workshop/planner.py` - Other BedrockModel usage examples