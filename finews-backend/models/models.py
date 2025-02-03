from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    conversations = relationship("Conversation", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True)
    thread_id = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="conversations")
    chat_history = relationship("ChatHistory", back_populates="conversation")
    news = relationship("News", back_populates="conversation")

class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("conversations.thread_id"), nullable=False)
    content = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    conversation = relationship("Conversation", back_populates="chat_history", foreign_keys=[thread_id])

class News(Base):
    __tablename__ = "news"
    
    id = Column(Integer, primary_key=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("conversations.thread_id"))
    content = Column(JSONB, nullable=True)
    link = Column(Text, nullable=True)
    query = Column(Text, nullable=True)
    source = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    conversation = relationship("Conversation", back_populates="news", foreign_keys=[thread_id])