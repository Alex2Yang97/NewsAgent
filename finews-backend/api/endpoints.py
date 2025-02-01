from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from db.database import get_db
from models.models import User, Conversation, Message
from api.auth import get_current_user, get_password_hash, create_access_token
from agents.news_agent import NewsAnalystAgent

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class ConversationCreate(BaseModel):
    title: str

class MessageCreate(BaseModel):
    content: str

@router.post("/users/", response_model=dict)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(
        username=user.username,
        email=user.email,
        password_hash=get_password_hash(user.password)
    )
    db.add(db_user)
    db.commit()
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/conversations/")
def create_conversation(
    conv: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = Conversation(user_id=current_user.id, title=conv.title)
    db.add(conversation)
    db.commit()
    return conversation

@router.post("/conversations/{conversation_id}/messages/")
def create_message(
    conversation_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify conversation belongs to user
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Create news analyst agent
    agent = NewsAnalystAgent(db=db)
    
    # Process message and get response
    result = agent.run(message.content, conversation_id)
    
    return {
        "conversation_id": conversation_id,
        "response": result["messages"][-1].content
    }

@router.get("/conversations/")
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).all()

@router.get("/conversations/{conversation_id}/messages/")
def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all() 