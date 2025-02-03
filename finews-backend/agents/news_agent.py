from loguru import logger
import json
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from itertools import chain
from typing import Annotated, List, Set

from langchain_core.messages.base import BaseMessage
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from agents.news_analyst_prompts import ARG_QUERY_PROMPT, ARG_ENTITIES_PROMPT, NEWS_ANALYST_AGENT_SYSTEM_PROMPT
from agents.utils import NewsAnalystState, get_llm, ModelName, retry_with_backoff
from tools.yfinance_news import yf_tool
from tools.ddg_search import ddg_search


@tool
def news_retriever(
    query: Annotated[str, ARG_QUERY_PROMPT],
    entities: Annotated[list[str], ARG_ENTITIES_PROMPT],
):
    """Tool that retrieves news, articles, and research reports"""
    return


class NewsAnalystAgent:
    def __init__(self, model_name: ModelName = ModelName.LLAMA_3_2, tracing: bool = False):
        logger.info("Initializing NewsAnalystAgent")
        self.tools = [news_retriever]
        self.model = get_llm(model_name, self.tools)
        self.thread_id = str(uuid4())
        if tracing:
            self.config = {
                "configurable": {
                    "thread_id": self.thread_id
                }
            }
        else:
            self.config = None

    def invoke_tools(self, query: str, entities: list[str]) -> List[dict]:
        """Execute multiple news retrieval tools in parallel"""
        logger.debug(f"Invoking news retrieval tools with query: {query}")
        tasks = [
            (partial(retry_with_backoff, ddg_search.invoke), query),
        ]
        if entities:
            for entity in entities:
                tasks.append(
                    (partial(retry_with_backoff, yf_tool.invoke), entity)
                )

        remove_duplicates: Set[str] = set()
        filtered_res_lst = []
        
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(func, *args) for func, *args in tasks]
            res_lst = [future.result() for future in futures]
            res_lst = list(chain.from_iterable(res_lst))

        for r in res_lst:
            if r and r["link"] not in remove_duplicates:
                remove_duplicates.add(r["link"])
                filtered_res_lst.append(r)
        
        logger.debug(f"Retrieved {len(filtered_res_lst)} unique news items")
        return filtered_res_lst

    def node_call_tools(self, state: NewsAnalystState) -> dict:
        """Handle tool calls and retrieve news"""
        tool_call = state["messages"][-1].tool_calls[0]
        query = tool_call["args"]["query"]
        entities = tool_call["args"]["entities"]
        logger.info(f"Processing tool call with query: {query}")

        response = self.invoke_tools(query, entities)
        logger.info(f"News retriever found {len(response)} articles")
        
        content = json.dumps([
            {
                "title": item["title"],
                "description": item["description"]
            } for item in response
        ])
        
        message = ToolMessage(
            content=content,
            name="news_retriever",
            tool_call_id=tool_call["id"],
        )
        
        logger.debug("News retriever message created successfully")
        return {
            "messages": [message],
            "metadata": {
                "news": response
            }
        }

    def call_model(self, state: NewsAnalystState, config: RunnableConfig) -> dict:
        """Call the LLM with the current state"""
        logger.debug("Calling LLM model")
        system_prompt = SystemMessage(NEWS_ANALYST_AGENT_SYSTEM_PROMPT)
        response = self.model.invoke([system_prompt] + state["messages"], config)
        logger.debug("LLM response received")
        return {"messages": [response]}

    @staticmethod
    def should_continue(state: NewsAnalystState) -> List[str]:
        """Determine if the agent should continue processing"""
        messages = state["messages"]
        last_message = messages[-1]
        if not last_message.tool_calls:
            logger.debug("No more tool calls, ending processing")
            return [END]
        logger.debug("Continuing with news retriever")
        return ["news_retriever"]

    def create_agent(self):
        """Create and configure the agent workflow"""
        logger.info("Creating news analyst agent workflow")
        workflow = StateGraph(NewsAnalystState)

        workflow.add_node("agent", self.call_model)
        workflow.add_node("news_retriever", self.node_call_tools)

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            ["news_retriever", END]
        )
        workflow.add_edge("news_retriever", "agent")

        logger.info("News analyst agent workflow created successfully")
        return workflow.compile()
    
    def run(self, msg_lst: list[BaseMessage]):
        """Run the news analyst agent"""
        agent = self.create_agent()
        res = agent.invoke(
            input={
                "messages": msg_lst,
                "metadata": {}
            },
            config=self.config
        )
        return res
    
    async def arun(self, msg_lst: list[BaseMessage]):
        """Run the news analyst agent asynchronously"""
        agent = self.create_agent()
        res = await agent.ainvoke(
            input={
                "messages": msg_lst,
                "metadata": {}
            },
            config=self.config
        )
        return res
    