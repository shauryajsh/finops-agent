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


# Once Gemini fails once in a run, stop retrying it - a quota error
# won't resolve again until the quota resets, so repeated attempts
# just waste time and repeat the same failure message.
_gemini_available = True


def ask_llm(prompt: str) -> str:
    """Sends a prompt to Gemini, falling back to Groq on any failure."""
    global _gemini_available

    if _gemini_available:
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"Gemini failed ({e}), switching to Groq for the rest of this run")
            _gemini_available = False

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq also failed ({e})")
        return "LLM_UNAVAILABLE: both providers failed for this request."


if __name__ == "__main__":
    print(ask_llm("Reply with exactly one word: hello"))