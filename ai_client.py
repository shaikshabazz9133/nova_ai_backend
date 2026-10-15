
import os
from dotenv import load_dotenv
from groq import AsyncGroq


load_dotenv()


api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

client = AsyncGroq(api_key=api_key, timeout=30.0, max_retries = 2)