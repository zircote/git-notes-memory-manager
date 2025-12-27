"""Adversarial content detection for implicit captures.

This module implements security screening for content before it's stored
as a memory. The detector uses an LLM to identify:

- Prompt injection attempts
- Data exfiltration patterns
- Code injection attempts
- Social engineering tactics
- Memory poisoning attempts

The detector is designed to be conservative - when in doubt, block.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import ThreatDetection, ThreatLevel
from .prompts import get_adversarial_prompt

if TYPE_CHECKING:
    from .llm_client import LLMClient

__all__ = [
    "AdversarialDetector",
    "DetectionResult",
    "get_adversarial_detector",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


@dataclass(frozen=True)
class DetectionResult:
    """Result of adversarial detection analysis.

    Attributes:
        detection: The threat detection result.
        analyzed_length: Length of content analyzed.
        error: Any error encountered during detection.
    """

    detection: ThreatDetection
    analyzed_length: int
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if detection succeeded without errors."""
        return self.error is None

    @property
    def should_block(self) -> bool:
        """Check if content should be blocked."""
        return self.detection.should_block


# =============================================================================
# Detector
# =============================================================================


@dataclass
class AdversarialDetector:
    """Detector for adversarial content patterns.

    Uses an LLM to analyze content for potential security threats
    before it's stored as a memory.

    Attributes:
        llm_client: LLM client for completions.
        fail_closed: If True, block on detection errors. Default True.
    """

    llm_client: LLMClient
    fail_closed: bool = True

    async def analyze(self, content: str) -> DetectionResult:
        """Analyze content for adversarial patterns.

        Args:
            content: The content to analyze.

        Returns:
            DetectionResult with threat assessment.
        """
        if not content.strip():
            return DetectionResult(
                detection=ThreatDetection.safe(),
                analyzed_length=0,
            )

        try:
            # Build the prompt
            prompt = get_adversarial_prompt(content)

            # Call LLM
            response = await self.llm_client.complete(
                prompt.user,
                system=prompt.system,
                json_mode=True,
            )

            # Parse response
            detection = self._parse_response(response.content)

            return DetectionResult(
                detection=detection,
                analyzed_length=len(content),
            )

        except Exception as e:
            error_msg = f"Adversarial detection failed: {e}"
            logger.warning(error_msg)

            # Fail closed: block on error if configured
            if self.fail_closed:
                return DetectionResult(
                    detection=ThreatDetection.blocked(
                        level=ThreatLevel.HIGH,
                        patterns=["detection_error"],
                        explanation=f"Detection failed, blocking as precaution: {e}",
                    ),
                    analyzed_length=len(content),
                    error=error_msg,
                )

            # Fail open: allow on error
            return DetectionResult(
                detection=ThreatDetection.safe(),
                analyzed_length=len(content),
                error=error_msg,
            )

    def _parse_response(self, content: str) -> ThreatDetection:
        """Parse LLM response into ThreatDetection.

        Args:
            content: JSON response from LLM.

        Returns:
            ThreatDetection with parsed threat info.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse adversarial response as JSON: %s", e)
            # Fail closed on parse error
            return ThreatDetection.blocked(
                level=ThreatLevel.MEDIUM,
                patterns=["json_parse_error"],
                explanation=f"Could not parse detection response: {e}",
            )

        # Parse threat level
        threat_level_str = data.get("threat_level", "none")
        try:
            threat_level = ThreatLevel(threat_level_str.lower())
        except ValueError:
            logger.warning("Unknown threat level: %s", threat_level_str)
            threat_level = ThreatLevel.MEDIUM

        # Parse patterns found
        patterns_raw = data.get("patterns_found", [])
        if isinstance(patterns_raw, list):
            patterns = tuple(str(p) for p in patterns_raw)
        else:
            patterns = ()

        # Parse should_block
        should_block_raw = data.get("should_block")
        if isinstance(should_block_raw, bool):
            should_block = should_block_raw
        else:
            # Infer from threat level if not provided or invalid
            should_block = threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

        # Parse explanation
        explanation = str(data.get("explanation", ""))

        return ThreatDetection(
            level=threat_level,
            patterns_found=patterns,
            explanation=explanation,
            should_block=should_block,
        )

    async def analyze_batch(
        self,
        contents: list[str],
    ) -> list[DetectionResult]:
        """Analyze multiple content pieces.

        Args:
            contents: List of content to analyze.

        Returns:
            List of DetectionResults in same order.
        """
        results: list[DetectionResult] = []
        for content in contents:
            result = await self.analyze(content)
            results.append(result)
        return results


# =============================================================================
# Factory
# =============================================================================

_detector: AdversarialDetector | None = None


def get_adversarial_detector() -> AdversarialDetector:
    """Get the default adversarial detector.

    Returns:
        AdversarialDetector configured from environment.

    Raises:
        SubconsciousnessDisabledError: If subconsciousness is disabled.
        LLMConfigurationError: If LLM is not configured.
    """
    global _detector
    if _detector is None:
        from . import get_llm_client

        _detector = AdversarialDetector(llm_client=get_llm_client())
    return _detector


def reset_default_detector() -> None:
    """Reset the default detector singleton.

    Useful for testing or reconfiguration.
    """
    global _detector
    _detector = None
