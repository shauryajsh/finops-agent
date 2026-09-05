"""LLM client with automatic fallback: Gemini first, Groq if that fails.

Both providers are free-tier; fallback exists for availability (rate
limits), not cost.
"""

import os
from dotenv import load_dotenv
from google import genai
from groq import Groq

load_dotenv()

# Providers periodically retire model names - if either fails with a 404,
# check ai.google.dev/gemini-api/docs/models or console.groq.com/docs/models
# for other model options to choose from
GEMINI_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "openai/gpt-oss-120b"

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])


def ask_llm(prompt: str) -> str:
    """Sends a prompt to Gemini, falling back to Groq on any failure."""
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Gemini failed ({e}), falling back to Groq")

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print(ask_llm("Reply with exactly one word: hello"))