import re
from pathlib import Path

def inspect_ingestion_ui():
    html = Path("frontend/ingestion.html").read_text(encoding="utf-8")
    
    # Check for copilot/chat elements
    print("Has chat input:", "copilot-input" in html or "chat-input" in html)
    print("Has chat send button:", "handleSendCopilotMessage" in html or "sendChatMessage" in html)
    print("Has interactive pills:", "copilot-pill" in html or "quick-prompt" in html)
    print("Has action buttons in chat:", "copilot-action-btn" in html)
    print("Has editor container:", "editor-container" in html or "rawPayloadEditor" in html)
    print("Has output tabs:", "output-tabs" in html or "tab-clean" in html)
    
    # Extract JavaScript function names related to chat and processing
    chat_funcs = re.findall(r"function\s+([a-zA-Z0-9_]*chat[a-zA-Z0-9_]*|[a-zA-Z0-9_]*copilot[a-zA-Z0-9_]*)", html, re.I)
    print("Chat functions in ingestion.html:", chat_funcs)
    
    proc_funcs = re.findall(r"function\s+([a-zA-Z0-9_]*process[a-zA-Z0-9_]*|[a-zA-Z0-9_]*convert[a-zA-Z0-9_]*|[a-zA-Z0-9_]*persist[a-zA-Z0-9_]*)", html, re.I)
    print("Process/persist functions in ingestion.html:", proc_funcs)

if __name__ == "__main__":
    inspect_ingestion_ui()
