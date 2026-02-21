# backend/api/routes/chat.py
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(message: str, session_id: str, user_id: str):
    """Send message to your existing root_agent"""
    try:
        # Use YOUR existing runner and root_agent
        message_content = types.Content(
            role='user',
            parts=[types.Part(text=message)]
        )
        
        # Collect the full response from your agent
        response_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message_content
        ):
            if hasattr(event, 'content') and hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text
        
        return {
            "response": response_text,
            "session_id": session_id,
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")