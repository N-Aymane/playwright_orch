import os
import asyncio
import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

async def test_copilot():
    github_pat = os.getenv("OPENAI_API_KEY")
    if not github_pat:
        print("No GITHUB_PAT / OPENAI_API_KEY set in .env")
        return
        
    print(f"Using GITHUB_PAT starting with: {github_pat[:12]}...")
    
    # 1. Exchange GitHub PAT for Copilot token
    async with httpx.AsyncClient() as http_client:
        try:
            # We need standard Headers for GitHub API request
            headers_list = [
                {
                    "Authorization": f"token {github_pat}",
                    "Editor-Version": "vscode/1.105.1",
                    "Editor-Plugin-Version": "copilot-chat/2.0.0",
                    "User-Agent": "GitHubCopilotChat/2.0.0",
                    "Accept": "application/json",
                },
                {
                    "Authorization": f"Bearer {github_pat}",
                    "Editor-Version": "vscode/1.105.1",
                    "Editor-Plugin-Version": "copilot-chat/2.0.0",
                    "User-Agent": "GitHubCopilotChat/2.0.0",
                    "Accept": "application/json",
                }
            ]
            
            copilot_token = None
            url = "https://api.github.com/copilot_internal/v2/token"
            
            for headers in headers_list:
                auth_header = headers["Authorization"]
                print(f"Exchanging token at: {url} with auth style '{auth_header[:15]}...'")
                res = await http_client.get(url, headers=headers)
                if res.status_code == 200:
                    token_data = res.json()
                    copilot_token = token_data.get("token")
                    print(f"Successfully retrieved Copilot token (starts with {copilot_token[:12]}...)")
                    break
                else:
                    print(f"Failed with status {res.status_code}: {res.text}")
            
            if not copilot_token:
                print("Could not retrieve copilot token with either header style.")
                return
                
        except Exception as e:
            print(f"Error during token exchange: {e}")
            return

    # 2. Call Copilot Chat endpoint with OpenAI Client
    client = AsyncOpenAI(
        api_key=copilot_token,
        base_url="https://api.githubcopilot.com"
    )
    
    # Try models
    models_to_test = ["gpt-4o", "gpt-4"]
    for model in models_to_test:
        try:
            print(f"\n--- Testing Copilot API with model {model} ---")
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "Respond with exactly 'OK' if you can read this."}
                ],
                max_tokens=10
            )
            print(f"Success! Response: {response.choices[0].message.content.strip()}")
            return
        except Exception as e:
            print(f"Failed for model {model}: {e}")

if __name__ == "__main__":
    asyncio.run(test_copilot())
