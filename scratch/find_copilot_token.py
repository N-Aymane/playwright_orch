import os
import json

paths = [
    os.path.expandvars(r"%APPDATA%\Code\User\globalStorage\github.copilot\hosts.json"),
    os.path.expandvars(r"%LOCALAPPDATA%\github-copilot\hosts.json"),
    os.path.expandvars(r"%USERPROFILE%\.config\github-copilot\hosts.json")
]

for p in paths:
    if os.path.exists(p):
        print(f"Found file: {p}")
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                # print keys of JSON to verify content structure safely
                print(f"Keys: {list(data.keys())}")
                # Print hosts
                for k, v in data.items():
                    if isinstance(v, dict):
                        print(f"Host '{k}' has keys: {list(v.keys())}")
                        if "oauth_token" in v:
                            print("  oauth_token found!")
        except Exception as e:
            print(f"Error reading {p}: {e}")
    else:
        print(f"Not found: {p}")
