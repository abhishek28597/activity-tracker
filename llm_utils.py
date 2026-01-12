"""
LLM utilities and response parsing for Activity Tracker.

Centralizes all LLM interaction, response parsing, and error handling.
"""

import json
from typing import List, Dict, Any, Optional
from groq import Groq
import os
from config import (
    LLM_MODEL_NAME,
    LLM_TEMPERATURE_REFINEMENT,
    LLM_TEMPERATURE_CONCEPT_EXTRACTION,
    LLM_TEMPERATURE_DAY_ACTIVITY,
    LLM_MAX_TOKENS_REFINEMENT,
    LLM_MAX_TOKENS_CONCEPT,
    LLM_MAX_TOKENS_AGGREGATE,
    LLM_MAX_TOKENS_DAY
)


def get_groq_client() -> Groq:
    """Get initialized Groq client."""
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))


def parse_json_response(response: str, fallback_parser=None) -> Any:
    """
    Parse LLM JSON response, handling markdown code blocks.

    Args:
        response: Raw LLM response text
        fallback_parser: Optional function to parse if JSON fails

    Returns:
        Parsed JSON object, or result of fallback_parser if provided

    Example:
        >>> response = '```json\\n["concept1", "concept2"]\\n```'
        >>> parse_json_response(response)
        ['concept1', 'concept2']
    """
    response = response.strip()

    # Handle markdown code blocks
    if response.startswith("```"):
        parts = response.split("```")
        if len(parts) >= 2:
            response = parts[1]
            # Remove language identifier (e.g., "json")
            if response.startswith("json"):
                response = response[4:]
            response = response.strip()

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        if fallback_parser:
            return fallback_parser(response)
        raise


def parse_list_response_fallback(response: str) -> List[str]:
    """
    Fallback parser for list responses when JSON parsing fails.
    Splits by newlines or commas and cleans up.
    """
    items = [
        item.strip().strip('"\'[]')
        for item in response.replace('\n', ',').split(',')
    ]
    return [item.lower() for item in items if item]


def call_llm(
    prompt: str,
    temperature: float = 0.5,
    max_tokens: int = 256,
    model: Optional[str] = None
) -> str:
    """
    Call Groq LLM with standard error handling.

    Args:
        prompt: User prompt text
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum completion tokens
        model: Model name (defaults to config.LLM_MODEL_NAME)

    Returns:
        LLM response text

    Raises:
        Exception: If LLM call fails
    """
    if model is None:
        model = LLM_MODEL_NAME

    client = get_groq_client()

    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )

    return completion.choices[0].message.content.strip()


def extract_concepts_from_llm(prompt: str) -> List[str]:
    """
    Extract concepts from LLM as a list of strings.
    Handles JSON parsing with fallback.

    Args:
        prompt: Prompt asking for concepts

    Returns:
        List of concept strings
    """
    response = call_llm(
        prompt,
        temperature=LLM_TEMPERATURE_CONCEPT_EXTRACTION,
        max_tokens=LLM_MAX_TOKENS_CONCEPT
    )

    try:
        concepts = parse_json_response(
            response,
            fallback_parser=parse_list_response_fallback
        )
        if isinstance(concepts, list):
            return [str(c).lower().strip() for c in concepts if c]
    except Exception as e:
        print(f"Warning: Concept extraction failed ({e}), using fallback")

    # Final fallback
    return parse_list_response_fallback(response)


def aggregate_concepts_via_llm(prompt: str) -> List[str]:
    """
    Aggregate concepts using LLM. Similar to extract but with different config.

    Args:
        prompt: Prompt asking for aggregation

    Returns:
        List of broader concept strings
    """
    response = call_llm(
        prompt,
        temperature=LLM_TEMPERATURE_CONCEPT_EXTRACTION,
        max_tokens=LLM_MAX_TOKENS_AGGREGATE
    )

    try:
        concepts = parse_json_response(
            response,
            fallback_parser=parse_list_response_fallback
        )
        if isinstance(concepts, list):
            return [str(c).lower().strip() for c in concepts if c]
    except Exception as e:
        print(f"Warning: Aggregation failed ({e}), using fallback")

    return parse_list_response_fallback(response)


def parse_mapping_response(response: str) -> Dict[str, str]:
    """
    Parse LLM mapping response (dict format).

    Args:
        response: LLM response containing JSON object

    Returns:
        Dictionary mapping concepts to broader categories
    """
    return parse_json_response(response, fallback_parser=lambda r: {})
