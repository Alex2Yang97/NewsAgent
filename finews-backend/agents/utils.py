import operator
from langchain_core.messages import HumanMessage, BaseMessage

from typing import Annotated, Any, Dict, Sequence, TypedDict
from enum import Enum
import json
import pandas as pd
import numpy as np
import time

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional

from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama


class ModelName(Enum):
    GPT_4_O_MINI = "gpt-4o-mini"
    LLAMA_3_2 = "llama3.2:latest"

def get_llm(model_name: ModelName, tools: list[BaseTool] = None, temperature: float = 0):
    if model_name == ModelName.GPT_4_O_MINI:
        model = ChatOpenAI(model=model_name.value, temperature=temperature)
    elif model_name == ModelName.LLAMA_3_2:
        model = ChatOllama(model=model_name.value, temperature=temperature)
    else:
        raise ValueError(f"Invalid model name: {model_name}")
    
    if tools:
        model = model.bind_tools(tools)
    
    return model


def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    return {**a, **b}


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    metadata: Annotated[Dict[str, Any], merge_dicts]


class NewsAnalystState(AgentState):
    pass

def retry_with_backoff(func, *args, max_retries=3, initial_delay=1):
    """Retry a function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func(*args)
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                print(f"Failed after {max_retries} attempts: {str(e)}")
                return []  # Return empty list on complete failure
            
            delay = initial_delay * (2 ** attempt)  # Exponential backoff
            print(f"error: {e}")
            print(f"Attempt {attempt + 1} failed, retrying in {delay} seconds...")
            time.sleep(delay)
    
    return []  # Fallback return if somehow we get here


