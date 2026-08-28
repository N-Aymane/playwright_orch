import os
import asyncio
from openai import AsyncOpenAI

async def test_keys():
    # 1. Test the GitHub PAT
    github_pat = os.getenv("OPENAI_API_KEY", "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")
    print(f"\n--- Testing GitHub PAT key: {github_pat[:15]}... ---")
    client1 = AsyncOpenAI(api_key=github_pat, base_url="https://openrouter.ai/api/v1")
    try:
        await client1.chat.completions.create(
            model="openai/gpt-4.1-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5
        )
    except Exception as e:
        print("Result:", e)

    # 2. Test a fake OpenRouter-formatted key
    fake_or_key = "sk-or-v1-0000000000000000000000000000000000000000000000000000000000000000"
    print(f"\n--- Testing Fake OpenRouter Key: {fake_or_key[:15]}... ---")
    client2 = AsyncOpenAI(api_key=fake_or_key, base_url="https://openrouter.ai/api/v1")
    try:
        await client2.chat.completions.create(
            model="openai/gpt-4.1-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5
        )
    except Exception as e:
        print("Result:", e)

    # 3. Test with no/empty key
    print("\n--- Testing Empty Key ---")
    client3 = AsyncOpenAI(api_key="", base_url="https://openrouter.ai/api/v1")
    try:
        await client3.chat.completions.create(
            model="openai/gpt-4.1-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5
        )
    except Exception as e:
        print("Result:", e)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_keys())
