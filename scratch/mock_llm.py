from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import sys

HOST = "localhost"
PORT = 8766

class MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Allow standard HTTP log to stderr so we see it in task log
        sys.stderr.write(f"[MOCK LLM] {format % args}\n")

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            
            messages = data.get("messages", [])
            system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "")
            
            print(f"\n--- RECEIVED REQUEST ---", flush=True)
            print(f"System Prompt (len={len(system_prompt)}): {system_prompt[:60]}...", flush=True)
            print(f"User Prompt (len={len(user_prompt)}): {user_prompt[:120]}...", flush=True)
            
            response_text = ""
            
            # Determine if it's the Planner calling
            if "planner" in system_prompt.lower() or "testing goal" in user_prompt.lower():
                print("-> Matched: PLANNER", flush=True)
                plan = [
                    {
                        "step_id": 1,
                        "description": "Navigate to registration page",
                        "action_type": "navigate",
                        "selector": "http://localhost:8765",
                        "selector_type": "css",
                        "value": "http://localhost:8765"
                    },
                    {
                        "step_id": 2,
                        "description": "Fill first name",
                        "action_type": "fill",
                        "selector": "#first-name",
                        "selector_type": "css",
                        "value": None
                    },
                    {
                        "step_id": 3,
                        "description": "Fill last name",
                        "action_type": "fill",
                        "selector": "#last-name",
                        "selector_type": "css",
                        "value": None
                    },
                    {
                        "step_id": 4,
                        "description": "Fill email",
                        "action_type": "fill",
                        "selector": "#email",
                        "selector_type": "css",
                        "value": None
                    },
                    {
                        "step_id": 5,
                        "description": "Select country",
                        "action_type": "select",
                        "selector": "#country",
                        "selector_type": "css",
                        "value": None
                    },
                    {
                        "step_id": 6,
                        "description": "Submit form",
                        "action_type": "click",
                        "selector": "#register-btn",
                        "selector_type": "css",
                        "value": None
                    },
                    {
                        "step_id": 7,
                        "description": "Assert registration success",
                        "action_type": "assert_text",
                        "selector": "body",
                        "selector_type": "css",
                        "value": "Registration Successful"
                    }
                ]
                response_text = json.dumps(plan)
                
            # Determine if it's the Executor calling
            elif "synthesiz" in system_prompt.lower() or "synthesiz" in user_prompt.lower() or "field description:" in user_prompt.lower():
                print("-> Matched: EXECUTOR DATA SYNTHESIS", flush=True)
                # Synthesize form values based on rules or description
                user_prompt_lower = user_prompt.lower()
                if "first name" in user_prompt_lower:
                    response_text = "Alex"
                elif "last name" in user_prompt_lower:
                    response_text = "Johnson"
                elif "email" in user_prompt_lower:
                    response_text = "test.user@example.com"
                elif "country" in user_prompt_lower:
                    response_text = "us"
                else:
                    response_text = "MockValue"
                print(f"   Synthesized Value: '{response_text}'", flush=True)
            
            else:
                print("-> Matched: NONE (Fallback to Default)", flush=True)
                response_text = "Default Mock Response"

            # Format response as OpenAI Chat Completion response
            response_data = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": response_text
                        },
                        "finish_reason": "stop",
                        "index": 0
                    }
                ]
            }
            
            encoded = json.dumps(response_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), MockLLMHandler)
    print(f"Mock LLM Server running at http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped Mock LLM Server.", flush=True)
