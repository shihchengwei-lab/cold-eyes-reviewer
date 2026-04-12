"""Tests for cold_eyes.noise.calibration."""

from unittest.mock import patch

from cold_eyes.noise.calibration import calibrate


class TestCalibrate:
    def test_no_evidence_high_downgraded(self):
        findings = [{"type": "review_finding", "confidence": "high"}]
        with patch("cold_eyes.noise.calibration._HAS_POLICY", False), \
             patch("cold_eyes.noise.calibration._HAS_MEMORY", False):
            result = calibrate(findings)
        assert result[0]["confidence"] == "medium"

    def test_with_message_kept_high(self):
        findings = [{"type": "review_finding", "confidence": "high", "message": "real issue"}]
        with patch("cold_eyes.noise.calibration._HAS_POLICY", False), \
             patch("cold_eyes.noise.calibration._HAS_MEMORY", False):
            result = calibrate(findings)
        assert result[0]["confidence"] == "high"

    def test_medium_not_downgraded(self):
        findings = [{"type": "review_finding", "confidence": "medium"}]
        with patch("cold_eyes.noise.calibration._HAS_POLICY", False), \
             patch("cold_eyes.noise.calibration._HAS_MEMORY", False):
            result = calibrate(findings)
        assert result[0]["confidence"] == "medium"

    def test_empty_findings(self):
        result = calibrate([])
        assert result == []

    def test_does_not_mutate_original(self):
        findings = [{"type": "review_finding", "confidence": "high"}]
        with patch("cold_eyes.noise.calibration._HAS_POLICY", False), \
             patch("cold_eyes.noise.calibration._HAS_MEMORY", False):
            calibrate(findings)
        assert findings[0]["confidence"] == "high"  # original unchanged

    def test_v1_calibration_path(self):
        findings = [{"type": "review_finding", "confidence": "high", "check": "x",
                     "file": "a.py", "severity": "major"}]
        fake_calibrated = [{"confidence": "medium"}]
        with patch("cold_eyes.noise.calibration._HAS_POLICY", True), \
             patch("cold_eyes.noise.calibration._HAS_MEMORY", True), \
             patch("cold_eyes.noise.calibration.extract_fp_patterns",
                   return_value={"total_overrides": 0}), \
             patch("cold_eyes.noise.calibration.calibrate_evidence",
                   return_value=fake_calibrated):
            result = calibrate(findings)
        assert result[0]["confidence"] == "medium"
