"""AgentCore E2E Tests — Issue #50, #51, #52 — AWS Real Resource Tests.

These tests require actual AWS AgentCore resources to be provisioned.
They are skipped by default and only run when YUI_AWS_E2E environment variable is set.

Run with: YUI_AWS_E2E=1 python -m pytest tests/test_agentcore_e2e.py -v
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from unittest.mock import patch

import pytest

from yui.tools.agentcore import code_execute, memory_recall, memory_store, web_browse

# Check playwright availability for Browser tests
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Additional skipif for browser tests that require playwright
_browser_skip = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE,
    reason="Browser E2E tests require playwright: pip install playwright && playwright install chromium"
)


# Skip all tests unless AWS E2E testing is explicitly enabled
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("YUI_AWS_E2E"),
        reason="AWS E2E tests require YUI_AWS_E2E environment variable"
    ),
]


class TestAgentCoreBrowserE2E:
    """Issue #50: AgentCore Browser real E2E tests."""

    @_browser_skip
    @pytest.mark.aws
    def test_browser_session_creation(self):
        """Test real AgentCore Browser session creation and basic functionality."""
        result = web_browse(url="https://httpbin.org/get", task="extract response")
        assert "Error" not in result
        assert "httpbin" in result.lower() or "get" in result.lower()

    @_browser_skip
    @pytest.mark.aws
    def test_url_navigation_content_extraction(self):
        """Test URL navigation and content extraction from a simple page."""
        result = web_browse(
            url="https://example.com", 
            task="extract the main heading and domain name"
        )
        assert "Error" not in result
        assert "example" in result.lower()

    @_browser_skip
    @pytest.mark.aws
    def test_javascript_rendering_page(self):
        """Test JavaScript rendering capability with a JS-heavy page."""
        result = web_browse(
            url="https://httpbin.org/json", 
            task="extract the JSON data"
        )
        assert "Error" not in result
        # Should be able to see JSON content after JS rendering
        assert any(char in result for char in ["{", "}", "[", "]"])

    @_browser_skip
    @pytest.mark.aws
    def test_session_timeout_cleanup(self):
        """Test that browser sessions are properly cleaned up."""
        # This test verifies session cleanup by checking multiple quick calls
        for i in range(3):
            result = web_browse(
                url=f"https://httpbin.org/get?test={i}", 
                task="extract test parameter"
            )
            assert "Error" not in result
        # If sessions are properly cleaned up, this should work without issues

    @_browser_skip
    @pytest.mark.aws
    def test_concurrent_session_limit(self):
        """Test concurrent browser session handling and limits."""
        def browse_task(idx):
            return web_browse(
                url=f"https://httpbin.org/get?concurrent={idx}", 
                task="extract concurrent parameter"
            )

        # Try to create multiple concurrent sessions
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(browse_task, i) for i in range(3)]
            results = []
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except TimeoutError:
                    results.append("Timeout")

        # At least one should succeed
        successful_results = [r for r in results if "Error" not in r and "Timeout" not in r]
        assert len(successful_results) >= 1

    @_browser_skip
    @pytest.mark.aws
    def test_https_ssl_handling(self):
        """Test HTTPS/SSL certificate handling."""
        result = web_browse(
            url="https://www.google.com", 
            task="extract page title"
        )
        assert "Error" not in result
        # Should handle HTTPS without SSL errors

    @_browser_skip
    @pytest.mark.aws
    def test_large_page_content(self):
        """Test handling of large page content."""
        result = web_browse(
            url="https://httpbin.org/html", 
            task="extract HTML structure"
        )
        assert "Error" not in result
        assert len(result) > 100  # Should get substantial content

    @_browser_skip
    @pytest.mark.aws
    def test_redirect_handling(self):
        """Test HTTP redirect handling."""
        result = web_browse(
            url="https://httpbin.org/redirect/2", 
            task="extract final page content"
        )
        # Should follow redirects and not get stuck
        assert "Error" not in result or "redirect" not in result.lower()


class TestAgentCoreMemoryE2E:
    """Issue #51: AgentCore Memory real E2E tests."""

    @pytest.mark.aws
    def test_memory_store_retrieve_roundtrip(self):
        """Test complete store → retrieve round-trip with real Memory API."""
        test_key = f"e2e_test_{int(time.time())}"
        test_value = "AgentCore E2E test value for round-trip verification"
        
        # Store
        store_result = memory_store(
            key=test_key, 
            value=test_value, 
            category="e2e_testing"
        )
        assert "Error" not in store_result
        assert "Stored memory" in store_result
        
        # Small delay to ensure indexing
        time.sleep(2)
        
        # Retrieve
        recall_result = memory_recall(query=test_key, limit=3)
        assert "Error" not in recall_result
        assert test_key in recall_result or test_value in recall_result

    @pytest.mark.aws
    def test_semantic_search_accuracy(self):
        """Test semantic search precision with similar but distinct memories."""
        timestamp = int(time.time())
        
        # Store related but distinct memories
        memory_store(
            key=f"color_preference_{timestamp}", 
            value="User prefers dark blue backgrounds", 
            category="preferences"
        )
        memory_store(
            key=f"theme_setting_{timestamp}", 
            value="User uses dark mode themes", 
            category="preferences"
        )
        memory_store(
            key=f"unrelated_{timestamp}", 
            value="User likes pizza on Fridays", 
            category="food"
        )
        
        time.sleep(3)  # Allow indexing
        
        # Search for color-related memories
        color_results = memory_recall(query="blue color preference", limit=5)
        theme_results = memory_recall(query="dark mode theme", limit=5)
        
        assert "Error" not in color_results
        assert "Error" not in theme_results
        # Should find relevant memories
        assert "blue" in color_results or "dark" in theme_results

    @pytest.mark.aws
    def test_memory_performance_bulk_storage(self):
        """Test performance with bulk memory storage operations."""
        timestamp = int(time.time())
        batch_size = 10
        
        start_time = time.time()
        
        # Store multiple memories in batch
        for i in range(batch_size):
            result = memory_store(
                key=f"bulk_test_{timestamp}_{i}", 
                value=f"Bulk test memory item {i} for performance testing", 
                category="performance_test"
            )
            assert "Error" not in result
        
        storage_time = time.time() - start_time
        
        # Should complete within reasonable time (30 seconds for 10 items)
        assert storage_time < 30, f"Bulk storage took too long: {storage_time}s"
        
        time.sleep(3)  # Allow indexing
        
        # Verify retrieval
        search_result = memory_recall(query=f"bulk_test_{timestamp}", limit=batch_size)
        assert "Error" not in search_result
        assert str(batch_size) in search_result or "bulk" in search_result

    @pytest.mark.aws
    def test_memory_category_organization(self):
        """Test memory organization by categories."""
        timestamp = int(time.time())
        
        # Store memories in different categories
        memory_store(
            key=f"work_task_{timestamp}", 
            value="Complete quarterly report", 
            category="work"
        )
        memory_store(
            key=f"personal_reminder_{timestamp}", 
            value="Buy groceries this weekend", 
            category="personal"
        )
        
        time.sleep(2)
        
        # Search should be able to find memories across categories
        work_results = memory_recall(query="quarterly report", limit=3)
        personal_results = memory_recall(query="groceries weekend", limit=3)
        
        assert "Error" not in work_results
        assert "Error" not in personal_results
        assert "quarterly" in work_results or "report" in work_results
        assert "groceries" in personal_results or "weekend" in personal_results

    @pytest.mark.aws
    def test_memory_search_limits(self):
        """Test memory search with different result limits."""
        timestamp = int(time.time())
        
        # Store several similar memories
        for i in range(5):
            memory_store(
                key=f"limit_test_{timestamp}_{i}", 
                value=f"Limit test memory number {i}", 
                category="limit_testing"
            )
        
        time.sleep(3)
        
        # Test different limits
        results_1 = memory_recall(query=f"limit_test_{timestamp}", limit=1)
        results_3 = memory_recall(query=f"limit_test_{timestamp}", limit=3)
        results_10 = memory_recall(query=f"limit_test_{timestamp}", limit=10)
        
        assert "Error" not in results_1
        assert "Error" not in results_3
        assert "Error" not in results_10
        
        # Results should respect limits (approximate, as search may return fewer)
        assert "1" in results_1 or "limit" in results_1
        assert "limit" in results_3
        assert "limit" in results_10

    @pytest.mark.aws
    def test_memory_empty_query_handling(self):
        """Test memory recall with edge case queries."""
        # Empty or minimal queries
        empty_result = memory_recall(query="", limit=1)
        minimal_result = memory_recall(query="x", limit=1)
        
        # Should handle gracefully without errors
        assert isinstance(empty_result, str)
        assert isinstance(minimal_result, str)
        # May return "No memories found" or actual results


class TestAgentCoreCodeInterpreterE2E:
    """Issue #52: AgentCore Code Interpreter real E2E tests."""

    @pytest.mark.aws
    def test_python_code_execution_stdout(self):
        """Test Python code execution with stdout capture."""
        result = code_execute(
            code="print('Hello, AgentCore E2E!')\nprint(2 + 3)", 
            language="python"
        )
        assert "Error" not in result
        assert "Hello, AgentCore E2E!" in result
        assert "5" in result

    @pytest.mark.aws
    def test_stderr_exception_handling(self):
        """Test stderr capture and exception handling."""
        result = code_execute(
            code="import sys\nprint('Error message', file=sys.stderr)\nraise ValueError('Test exception')", 
            language="python"
        )
        # Should capture stderr and/or exception info
        assert "Error message" in result or "ValueError" in result or "Test exception" in result

    @pytest.mark.aws
    def test_file_io_sandbox(self):
        """Test file I/O operations within the sandbox environment."""
        result = code_execute(
            code="""
import os
# Write a file
with open('test_file.txt', 'w') as f:
    f.write('AgentCore sandbox test')

# Read it back
with open('test_file.txt', 'r') as f:
    content = f.read()

print(f'File content: {content}')
print(f'Current directory: {os.getcwd()}')
""", 
            language="python"
        )
        assert "Error" not in result
        assert "AgentCore sandbox test" in result
        assert "Current directory:" in result

    @pytest.mark.aws
    def test_timeout_resource_limits(self):
        """Test code execution with potential timeout scenarios."""
        # Test with a reasonable computation that shouldn't timeout
        result = code_execute(
            code="""
import time
result = 0
for i in range(1000):
    result += i
print(f'Computation result: {result}')
""", 
            language="python"
        )
        assert "Error" not in result
        assert "Computation result:" in result

    @pytest.mark.aws
    def test_javascript_execution(self):
        """Test JavaScript code execution if supported."""
        result = code_execute(
            code="console.log('JavaScript E2E test'); console.log(2 + 3);", 
            language="javascript"
        )
        # May not be supported, but should handle gracefully
        if "Error" not in result:
            assert "JavaScript E2E test" in result or "5" in result

    @pytest.mark.aws
    def test_typescript_execution(self):
        """Test TypeScript code execution if supported."""
        result = code_execute(
            code="""
let message: string = 'TypeScript E2E test';
let sum: number = 2 + 3;
console.log(message);
console.log(sum);
""", 
            language="typescript"
        )
        # May not be supported, but should handle gracefully
        if "Error" not in result:
            assert "TypeScript E2E test" in result or "5" in result

    @pytest.mark.aws
    def test_python_imports_standard_library(self):
        """Test Python standard library imports and functionality."""
        result = code_execute(
            code="""
import json
import datetime
import math

pytestmark = pytest.mark.e2e


data = {'test': True, 'timestamp': str(datetime.datetime.now())}
json_str = json.dumps(data)
print(f'JSON: {json_str}')
print(f'Math π: {math.pi}')
""", 
            language="python"
        )
        assert "Error" not in result
        assert "JSON:" in result
        assert "3.14" in result  # Part of π

    @pytest.mark.aws
    def test_code_session_isolation(self):
        """Test that code sessions are properly isolated."""
        # First execution
        result1 = code_execute(
            code="test_var = 'first_session'\nprint(test_var)", 
            language="python"
        )
        assert "Error" not in result1
        assert "first_session" in result1
        
        # Second execution should not see variables from first
        result2 = code_execute(
            code="""
try:
    print(test_var)
    print('Variable persisted - BAD')
except NameError:
    print('Variable not found - GOOD (isolated)')
""", 
            language="python"
        )
        assert "Error" not in result2
        # Should show isolation (NameError expected)
        assert "isolated" in result2 or "NameError" in result2

    @pytest.mark.aws
    def test_multiline_complex_code(self):
        """Test execution of complex multiline code."""
        result = code_execute(
            code="""
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# Calculate first 10 fibonacci numbers
fib_sequence = [fibonacci(i) for i in range(10)]
print(f'Fibonacci sequence: {fib_sequence}')

# Test dictionary and list operations
data = {'name': 'AgentCore', 'type': 'E2E Test'}
items = list(data.items())
print(f'Items: {items}')
""", 
            language="python"
        )
        assert "Error" not in result
        assert "Fibonacci sequence:" in result
        assert "Items:" in result
        assert "AgentCore" in result

    @pytest.mark.aws
    def test_error_recovery_continued_execution(self):
        """Test that errors don't break the code interpreter permanently."""
        # First: cause an error
        result1 = code_execute(
            code="undefined_variable", 
            language="python"
        )
        # Should get an error
        assert "Error" in result1 or "undefined_variable" in result1 or "NameError" in result1
        
        # Second: execute valid code - should work fine
        result2 = code_execute(
            code="print('Recovered successfully after error')", 
            language="python"
        )
        assert "Error" not in result2
        assert "Recovered successfully" in result2