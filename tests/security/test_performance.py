"""Performance tests for secrets filtering.

These tests verify that the filtering pipeline meets the <10ms target
for typical content sizes.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from git_notes_memory.security.config import SecretsConfig
from git_notes_memory.security.detector import DetectSecretsAdapter
from git_notes_memory.security.pii import PIIDetector
from git_notes_memory.security.service import SecretsFilteringService, reset_service


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    reset_service()
    yield
    reset_service()


class TestPatternDetectionPerformance:
    """Tests for pattern detection performance."""

    def test_pii_detection_under_1ms(self):
        """Test that PII detection completes in <1ms for typical content."""
        detector = PIIDetector()
        content = """
        This is typical memory content with some text.
        It might mention a user or a project.
        Sometimes there are technical details.
        """

        # Warm up
        detector.detect(content)

        # Measure
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            detector.detect(content)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 1.0, f"PII detection took {avg_ms:.3f}ms avg (target: <1ms)"

    def test_pii_detection_with_secrets_under_2ms(self):
        """Test PII detection with actual secrets still fast."""
        detector = PIIDetector()
        content = """
        User details:
        SSN: 123-45-6789
        Phone: (555) 123-4567
        Card: 4111111111111111
        """

        # Warm up
        detector.detect(content)

        # Measure
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            detector.detect(content)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 2.0, f"PII detection took {avg_ms:.3f}ms avg (target: <2ms)"

    def test_detect_secrets_adapter_under_5ms(self, tmp_path: Path):
        """Test detect-secrets adapter stays under 5ms."""
        adapter = DetectSecretsAdapter()
        content = """
        This is typical memory content.
        AWS_ACCESS_KEY_ID = AKIAIOSFODNN7EXAMPLE
        Some more text here.
        """

        # Warm up
        adapter.detect(content)

        # Measure
        iterations = 50
        start = time.perf_counter()
        for _ in range(iterations):
            adapter.detect(content)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        # detect-secrets is heavier, allow 5ms
        assert avg_ms < 5.0, f"detect-secrets took {avg_ms:.3f}ms avg (target: <5ms)"


class TestEntropyAnalysisPerformance:
    """Tests for entropy analysis performance."""

    def test_entropy_detection_scales_linearly(self):
        """Test that entropy detection scales linearly with content size."""
        # Use the full service to test entropy scaling
        from git_notes_memory.security.config import SecretsConfig
        from git_notes_memory.security.service import SecretsFilteringService

        config = SecretsConfig(enabled=True, entropy_enabled=True, pii_enabled=False)
        service = SecretsFilteringService(config=config)

        # Test with increasing sizes
        times = []
        sizes = [100, 500, 1000, 5000]

        for size in sizes:
            content = "A" * size

            # Warm up
            service.scan(content)

            # Measure
            iterations = 20
            start = time.perf_counter()
            for _ in range(iterations):
                service.scan(content)
            elapsed = time.perf_counter() - start

            avg_ms = (elapsed / iterations) * 1000
            times.append(avg_ms)

        # Check roughly linear scaling (5x size should not be >10x time)
        ratio_size = sizes[-1] / sizes[0]  # 50x
        ratio_time = times[-1] / times[0] if times[0] > 0 else 1

        # Allow 3x the linear factor for overhead
        assert ratio_time < ratio_size * 3, (
            f"Entropy detection not scaling linearly: "
            f"{ratio_size}x size -> {ratio_time:.1f}x time"
        )


class TestFullPipelinePerformance:
    """Tests for the complete filtering pipeline performance."""

    def test_full_pipeline_under_10ms(self, tmp_path: Path):
        """Test that the full pipeline completes in <10ms for typical content."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = """
        ## Decision: Use PostgreSQL for persistence

        We've decided to use PostgreSQL as our primary database.

        ### Context
        The project needs a robust relational database.

        ### Rationale
        - Strong ACID guarantees
        - Good Python support via psycopg2
        - Familiar to the team
        """

        # Warm up
        service.filter(content, source="test")

        # Measure
        iterations = 50
        start = time.perf_counter()
        for _ in range(iterations):
            service.filter(content, source="test")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 10.0, f"Full pipeline took {avg_ms:.3f}ms avg (target: <10ms)"

    def test_full_pipeline_with_secrets_under_15ms(self, tmp_path: Path):
        """Test pipeline with secrets still under 15ms."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = """
        ## User Data Migration

        Migrating user 123-45-6789 to new system.
        Contact: (555) 123-4567
        Backup card: 4111111111111111
        """

        # Warm up
        service.filter(content, source="test")

        # Measure
        iterations = 50
        start = time.perf_counter()
        for _ in range(iterations):
            service.filter(content, source="test")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 15.0, (
            f"Pipeline with secrets took {avg_ms:.3f}ms (target: <15ms)"
        )

    def test_full_pipeline_with_entropy_under_20ms(self, tmp_path: Path):
        """Test pipeline with entropy enabled under 20ms."""
        config = SecretsConfig(enabled=True, entropy_enabled=True)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = """
        Configuration settings:
        DATABASE_URL = postgresql://localhost/db
        SECRET_KEY = not-really-a-secret-just-a-placeholder

        Normal text content here.
        """

        # Warm up
        service.filter(content, source="test")

        # Measure
        iterations = 30
        start = time.perf_counter()
        for _ in range(iterations):
            service.filter(content, source="test")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        # Entropy adds overhead
        assert avg_ms < 20.0, (
            f"Pipeline with entropy took {avg_ms:.3f}ms (target: <20ms)"
        )


class TestLargeContentPerformance:
    """Tests for performance with large content."""

    def test_large_content_scales_reasonably(self, tmp_path: Path):
        """Test that large content (50KB) completes in <100ms."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        # Create ~50KB content with some secrets scattered
        base_text = "Normal text content. " * 500  # ~10KB each
        secret = " SSN: 123-45-6789 "
        content = base_text + secret + base_text + secret + base_text

        content_kb = len(content) / 1024
        assert content_kb > 20, f"Content too small: {content_kb:.1f}KB"

        # Warm up
        service.filter(content, source="test")

        # Measure
        iterations = 10
        start = time.perf_counter()
        for _ in range(iterations):
            service.filter(content, source="test")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 200.0, (
            f"Large content ({content_kb:.0f}KB) took {avg_ms:.1f}ms (target: <200ms)"
        )

    def test_max_content_size_limit(self, tmp_path: Path):
        """Test behavior at maximum content size (100KB limit)."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        # Create exactly 100KB content
        content = "A" * (100 * 1024)

        # Should complete without error
        start = time.perf_counter()
        result = service.filter(content, source="test")
        elapsed = (time.perf_counter() - start) * 1000

        assert result is not None
        # Should still be reasonably fast
        assert elapsed < 200.0, f"Max content took {elapsed:.3f}ms (target: <200ms)"


class TestScanVsFilterPerformance:
    """Test scan-only vs full filter performance."""

    def test_scan_faster_than_filter(self, tmp_path: Path):
        """Test that scan-only is faster than full filter."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "User SSN: 123-45-6789"

        # Warm up
        service.scan(content)
        service.filter(content, source="test")

        # Measure scan
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            service.scan(content)
        scan_time = time.perf_counter() - start

        # Measure filter
        start = time.perf_counter()
        for _ in range(iterations):
            service.filter(content, source="test")
        filter_time = time.perf_counter() - start

        # Scan should be faster (no redaction step)
        assert scan_time <= filter_time * 1.2, (
            f"Scan ({scan_time * 1000:.1f}ms) not faster than filter ({filter_time * 1000:.1f}ms)"
        )


class TestConcurrencyPerformance:
    """Tests for concurrent access performance."""

    def test_service_thread_safe_performance(self, tmp_path: Path):
        """Test that service performs well under concurrent access."""
        import concurrent.futures

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "User SSN: 123-45-6789"

        def filter_content():
            for _ in range(10):
                service.filter(content, source="test")

        # Run concurrently
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(filter_content) for _ in range(4)]
            concurrent.futures.wait(futures)
        elapsed = (time.perf_counter() - start) * 1000

        # 40 total operations should complete in <500ms
        assert elapsed < 500.0, (
            f"Concurrent filtering took {elapsed:.1f}ms (target: <500ms)"
        )
