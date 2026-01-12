"""
LLM Refiner Pipeline

Uses Groq's Llama 3.3 70B model to refine raw keystroke text into a cleaner,
structured format with timestamps and app context.
"""

import os
from dotenv import load_dotenv
from llm_utils import get_groq_client
from config import (
    LLM_MODEL_NAME,
    LLM_TEMPERATURE_REFINEMENT,
    LLM_MAX_TOKENS_REFINEMENT
)

# Load environment variables from .env file
load_dotenv()

SYSTEM_PROMPT = """You are a text refinement assistant. Your task is to take raw keystroke logs and transform them into clean, readable text.

The input will contain timestamps and raw text captured from keystrokes across different applications.

Your output should follow this exact format:
[timestamp]
[app name]
Refined, grammatically correct text.

Rules:
1. Fix typos and grammatical errors
2. Group related content together under the same timestamp/app
3. Preserve the meaning and intent of the original text
4. Format commands and code snippets appropriately
5. Remove gibberish or accidental keystrokes
6. Keep timestamps in the format provided (e.g., "8 Jan 2026 at 1:00 AM")
7. Identify the likely application from context clues (e.g., terminal commands → "Terminal", browsing → app name, coding → "Code Editor")
8. If multiple apps are detected within the same time block, separate them with blank lines
9. Do not add any commentary or explanations - only output the refined text
10. Preserve line breaks where they make sense (e.g., separate commands, paragraphs)"""


def refine_text(raw_text: str) -> str:
    """
    Refine raw keystroke text using Groq's LLM.
    
    Args:
        raw_text: Raw text reconstructed from keystrokes
        
    Returns:
        Refined text in structured format
    """
    if not raw_text or not raw_text.strip():
        return raw_text
    
    try:
        client = get_groq_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Please refine the following raw keystroke log:\n\n{raw_text}"
                }
            ],
            model=LLM_MODEL_NAME,
            temperature=LLM_TEMPERATURE_REFINEMENT,
            max_completion_tokens=LLM_MAX_TOKENS_REFINEMENT,
        )
        
        refined = chat_completion.choices[0].message.content
        return refined if refined else raw_text
        
    except Exception as e:
        # If LLM call fails, return original text with error note
        print(f"LLM refinement failed: {e}")
        return f"[Refinement failed: {str(e)}]\n\n{raw_text}"


if __name__ == "__main__":
    # Test the refiner with sample text
    sample = """8 Jan 2026 at 1:00 AM
okay let me test this and see hwo this works
 - you create a readme.md for this repo that explains the functioaning also
create readme.md
Add this app screenshot as well to read - vscnreenshot.pn
Move the screenshot.png into a assets folder and keep it insifde that for cleaner code"""
    
    print("Original:")
    print(sample)
    print("\n" + "="*50 + "\n")
    print("Refined:")
    print(refine_text(sample))

