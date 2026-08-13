import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env
load_dotenv()

async def test_api():
    api_key = os.getenv("OPENAI_API_KEY")
    # We will test both the user's key and see if we can query models
    base_urls = ["https://models.github.ai/inference", "https://models.inference.ai.azure.com"]
    
    for base_url in base_urls:
        print(f"\n====================================")
        print(f"Testing base URL: {base_url}")
        print(f"====================================")
        
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        models_to_test = ["gpt-4o-mini", "gpt-4o"]
        
        for model in models_to_test:
            try:
                print(f"--- Testing model: {model} ---")
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": "Hello, respond with exactly 'OK' if you can read this."}
                    ],
                    max_tokens=10
                )
                print(f"Success! Response: {response.choices[0].message.content.strip()}")
                return
            except Exception as e:
                print(f"Failed for model {model}: {e}")
            
if __name__ == "__main__":
    asyncio.run(test_api())
