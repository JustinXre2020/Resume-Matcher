"""
Recipient configuration for Job Hunter Sentinel
Supports multi-recipient with per-recipient search terms and sponsorship needs
"""
import os
import json
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Recipient:
    """Recipient configuration with search preferences"""
    email: str
    needs_sponsorship: bool
    search_terms: List[str]


def parse_recipients() -> List[Recipient]:
    """
    Parse recipient configuration from environment variables.

    Priority:
    1. RECIPIENTS (JSON array) - new format with per-recipient search terms
    2. RECIPIENT_EMAIL (string) - legacy fallback with global SEARCH_TERMS

    Returns:
        List of Recipient objects

    Raises:
        ValueError: If no valid recipient configuration found
    """
    # Try new JSON format first
    recipients_json = os.getenv("RECIPIENTS")

    if recipients_json:
        try:
            recipients_data = json.loads(recipients_json)
            recipients = []

            for r in recipients_data:
                email = r.get("email")
                if not email:
                    continue

                needs_sponsorship = r.get("needs_sponsorship", True)
                search_terms = r.get("search_terms", [])

                # Validate search_terms is a list
                if isinstance(search_terms, str):
                    search_terms = [term.strip() for term in search_terms.split(",") if term.strip()]
                elif not isinstance(search_terms, list):
                    search_terms = []

                recipients.append(Recipient(
                    email=email,
                    needs_sponsorship=needs_sponsorship,
                    search_terms=search_terms
                ))

            if recipients:
                print(f"   Loaded {len(recipients)} recipient(s) from RECIPIENTS config")
                return recipients

        except json.JSONDecodeError as e:
            print(f"   Warning: Invalid RECIPIENTS JSON: {e}")
            # Fall through to legacy format

    # Legacy fallback: single recipient with global search terms
    recipient_email = os.getenv("RECIPIENT_EMAIL")

    if not recipient_email:
        raise ValueError(
            "No recipient configuration found. "
            "Set RECIPIENTS (JSON) or RECIPIENT_EMAIL environment variable."
        )

    # Get global search terms for legacy mode
    search_terms_str = os.getenv("SEARCH_TERMS", "entry level software engineer")
    search_terms = [term.strip() for term in search_terms_str.split(",") if term.strip()]

    print(f"   Using legacy config: {recipient_email} (needs_sponsorship=True)")

    return [Recipient(
        email=recipient_email,
        needs_sponsorship=True,  # Legacy default
        search_terms=search_terms
    )]


def get_all_search_terms(recipients: List[Recipient]) -> List[str]:
    """
    Collect all unique search terms across all recipients.

    Args:
        recipients: List of Recipient objects

    Returns:
        List of unique search terms (preserves first occurrence order)
    """
    seen = set()
    unique_terms = []

    for recipient in recipients:
        for term in recipient.search_terms:
            term_lower = term.lower().strip()
            if term_lower and term_lower not in seen:
                seen.add(term_lower)
                unique_terms.append(term.strip())

    return unique_terms


def main():
    """Test configuration parsing"""
    print("Testing configuration parsing...\n")

    # Test with current env
    try:
        recipients = parse_recipients()
        print(f"\nParsed {len(recipients)} recipient(s):")
        for r in recipients:
            print(f"  - {r.email}")
            print(f"    needs_sponsorship: {r.needs_sponsorship}")
            print(f"    search_terms: {r.search_terms}")

        all_terms = get_all_search_terms(recipients)
        print(f"\nAll unique search terms: {all_terms}")

    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
