"""PII redaction using Microsoft Presidio with spaCy NLP engine."""

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


class Redactor:
    def __init__(self) -> None:
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()

    def redact(self, text: str) -> str:
        """Replace detected PII with [REDACTED_<TYPE>] tokens.

        Returns text unchanged if no PII is detected.
        """
        results = self._analyzer.analyze(text=text, language="en")
        if not results:
            return text
        operators = {
            r.entity_type: OperatorConfig(
                "replace", {"new_value": f"[REDACTED_{r.entity_type}]"}
            )
            for r in results
        }
        return self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        ).text


def build_redactor() -> Redactor:
    """Construct the Redactor, loading the spaCy model. Call once from lifespan."""
    return Redactor()
