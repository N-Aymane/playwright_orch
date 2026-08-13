import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

async def list_models():
    api_key = os.getenv("OPENAI_API_KEY")
    
    # 1. Test OpenRouter
    print("\n--- Listing models from OpenRouter ---")
    client = AsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    try:
        models = await client.models.list()
        print("Success OpenRouter! Found models:", [m.id for m in models.data[:5]])
    except Exception as e:
        print("Failed OpenRouter:", e)
        
    # 2. Test Azure Inference / GitHub Models
    print("\n--- Listing models from Azure Inference ---")
    azure_client = AsyncOpenAI(api_key=api_key, base_url="https://models.inference.ai.azure.com")
    try:
        models = await azure_client.models.list()
        print("Success Azure! Found models:", [m.id for m in models.data[:5]])
    except Exception as e:
        print("Failed Azure:", e)

if __name__ == "__main__":
    asyncio.run(list_models())
