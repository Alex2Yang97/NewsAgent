import json
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from langchain_core.messages.base import BaseMessage
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from db.database import get_db
from models.models import User, Conversation, ChatHistory, News
from agents.news_agent import NewsAnalystAgent
from utils.fake_user import get_user_by_id

router = APIRouter()

class ConversationCreate(BaseModel):
    title: str

class MessageCreate(BaseModel):
    content: str


def msg_to_json(msg_lst: list[BaseMessage]):
    msg_json_lst = []

    for msg in msg_lst:
        if isinstance(msg, ToolMessage):
            msg_json_lst.append({"tool": msg.model_dump_json()})
        elif isinstance(msg, AIMessage):
            msg_json_lst.append({"ai": msg.model_dump_json()})
        elif isinstance(msg, HumanMessage):
            msg_json_lst.append({"human": msg.model_dump_json()})
        elif isinstance(msg, SystemMessage):
            msg_json_lst.append({"system": msg.model_dump_json()})
        else:
            raise ValueError(f"Unknown message type: {type(msg)}")

    return msg_json_lst


def msg_from_json(msg_json_lst: list[dict]):
    msg_lst = []
    print(f"alex-debug msg_json_lst: {msg_json_lst}")
    for msg_json in msg_json_lst:
        print(f"alex-debug msg_json: {msg_json}")
        if "tool" in msg_json:
            msg_lst.append(ToolMessage(**json.loads(msg_json["tool"])))
        elif "ai" in msg_json:
            msg_lst.append(AIMessage(**json.loads(msg_json["ai"])))
        elif "human" in msg_json:
            msg_lst.append(HumanMessage(**json.loads(msg_json["human"])))
        elif "system" in msg_json:
            msg_lst.append(SystemMessage(**json.loads(msg_json["system"])))
        else:
            raise ValueError(f"Unknown message type: {msg_json}")

    return msg_lst


@router.get("/conversations/{thread_id}/messages")
async def retrieve_conversation(
    thread_id: str,
    db: AsyncSession = Depends(get_db)
):
    # Use fake user
    current_user = await get_user_by_id(1)
    
    # Verify conversation exists and belongs to user
    stmt = select(Conversation).where(
        Conversation.thread_id == thread_id,
        Conversation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=404, 
            detail="Conversation not found or you don't have access"
        )
    
    # Get chat history
    stmt = select(ChatHistory).where(
        ChatHistory.thread_id == thread_id
    ).order_by(ChatHistory.created_at.asc())
    result = await db.execute(stmt)
    msg_lst = []
    for row in result.scalars().all():
        msg_lst.extend(msg_from_json(row.content))
    return msg_lst


@router.post("/chat")
async def chat_news_agent(
    message: MessageCreate,
    thread_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Use fake user
    current_user = await get_user_by_id()
    
    conversation = None
    
    logger.debug(f"alex-debug thread_id: {thread_id}")
    if thread_id:
        # Verify conversation exists and belongs to user
        stmt = select(Conversation).where(
            Conversation.thread_id == thread_id,
            Conversation.user_id == current_user.id
        )
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found or you don't have access"
            )
            
        # Extract messages from ChatHistory based on conversation.thread_id
        stmt = select(ChatHistory).where(
            ChatHistory.thread_id == conversation.thread_id
        ).order_by(ChatHistory.created_at.asc())
        result = await db.execute(stmt)
        chat_history = []
        for row in result.scalars().all():
            chat_history.extend(row.content)
        
        # Convert chat history to list of messages
        chat_history_msg_lst = msg_from_json(chat_history)
        
    else:
        chat_history_msg_lst = []
    
    logger.debug(f"alex-debug chat_history_msg_lst: {chat_history_msg_lst}")
    # Create news analyst agent
    agent = NewsAnalystAgent()
    
    msg_lst = chat_history_msg_lst + [HumanMessage(content=message.content)]
    
    # Process message and get response
    result = await agent.arun(msg_lst)
    result["messages"] = result["messages"][len(chat_history_msg_lst):]
    
    logger.debug(f"alex-debug result: {result}")
    
    if not conversation:
        logger.debug(f"alex-debug create new conversation")
        # Create new conversation
        conversation = Conversation(
            user_id=current_user.id,
            title=message.content,
            thread_id=agent.thread_id
        )
        
        db.add(conversation)
    
    logger.debug(f"alex-debug create chat history")
    conversation_to_db = msg_to_json(result["messages"])
    user_message = ChatHistory(
        thread_id=conversation.thread_id,
        content=conversation_to_db
    )
    db.add(user_message)
    
    await db.commit()
    await db.refresh(conversation)
    await db.refresh(user_message)
    
    # Store news items if present in metadata
    if "news" in result["metadata"]:
        logger.debug(f"alex-debug store news items")
        try:
            news_content_to_db = []
            for news_item in result["metadata"]["news"]:
                news_content_to_db.append({
                    "title": news_item.get("title", None),
                    "description": news_item.get("description", None),
                    "content": news_item.get("content", None),
                })
                news = News(
                    thread_id=conversation.thread_id,
                    content=news_content_to_db,
                    link=news_item.get("link", None),
                    query=news_item.get("query", None),
                    source=news_item.get("source", None)
                )
                db.add(news)
                await db.commit()
        except Exception as e:
            logger.error(f"Error processing news items: {e}")


    return {
        "thread_id": conversation.thread_id,
        "response": result
    }

@router.get("/conversations/{thread_id}/news")
async def retrieve_news(
    thread_id: str,
    db: AsyncSession = Depends(get_db)
):
    # Use fake user
    current_user = await get_user_by_id()
    
    # Verify conversation exists and belongs to user
    stmt = select(Conversation).where(
        Conversation.thread_id == thread_id,
        Conversation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access"
        )
    
    # Get news related to the conversation
    stmt = select(News).where(
        News.thread_id == conversation.thread_id
    ).order_by(News.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()