import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

async def diagnostic():
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    llm_model = os.getenv("LLM_MODEL")
    
    print(f"OPENAI_API_KEY: {api_key[:15]}... (length: {len(api_key)})" if api_key else "OPENAI_API_KEY: NOT SET")
    print(f"OPENAI_API_BASE: {api_base}")
    print(f"LLM_MODEL: {llm_model}")
    
    # 1. Test OpenRouter (if that's the base URL)
    print("\n--- Testing OpenRouter with current base URL ---")
    client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    try:
        response = await client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5
        )
        print("Success OpenRouter:", response.choices[0].message.content)
    except Exception as e:
        print("Failed OpenRouter:", e)
        
    # 2. Test Azure Inference / GitHub Models
    print("\n--- Testing Azure Inference ---")
    azure_client = AsyncOpenAI(api_key=api_key, base_url="https://models.inference.ai.azure.com")
    try:
        response = await azure_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5
        )
        print("Success Azure:", response.choices[0].message.content)
    except Exception as e:
        print("Failed Azure:", e)

if __name__ == "__main__":
    asyncio.run(diagnostic())
