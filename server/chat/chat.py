from fastapi import Body
from fastapi.responses import StreamingResponse
from configs.model_config import llm_model_dict, LLM_MODEL
from server.chat.utils import wrap_done
from langchain.chat_models import ChatOpenAI
from langchain import LLMChain
from langchain.callbacks import AsyncIteratorCallbackHandler
from typing import AsyncIterable
import asyncio
from langchain.prompts.chat import ChatPromptTemplate
from typing import List
from server.chat.utils import History


def chat(query: str = Body(..., description="用户输入", examples=["恼羞成怒"]),
         history: List[History] = Body([],
                                       description="历史对话",
                                       examples=[[
                                           {"role": "user", "content": "我们来玩成语接龙，我先来，生龙活虎"},
                                           {"role": "assistant", "content": "虎头虎脑"}]]
                                       ),
         stream: bool = Body(False, description="流式输出"),
         ):
    history = [History(**h) if isinstance(h, dict) else h for h in history]

    async def chat_iterator(query: str,
                            history: List[History] = [],
                            ) -> AsyncIterable[str]:
        callback = AsyncIteratorCallbackHandler()

        model = ChatOpenAI(
            streaming=True,
            verbose=True,
            callbacks=[callback],
            openai_api_key=llm_model_dict[LLM_MODEL]["api_key"],
            openai_api_base=llm_model_dict[LLM_MODEL]["api_base_url"],
            model_name=LLM_MODEL,
            openai_proxy=llm_model_dict[LLM_MODEL].get("openai_proxy")
        )

        chat_prompt = ChatPromptTemplate.from_messages(
            [i.to_msg_tuple() for i in history] + [("human", "{input}")])
        chain = LLMChain(prompt=chat_prompt, llm=model)

        # Begin a task that runs in the background.
        task = asyncio.create_task(wrap_done(
            chain.acall({"input": query}),
            callback.done),
        )

        if stream:
            async for token in callback.aiter():
                # Use server-sent-events to stream the response
                yield token
        else:
            answer = ""
            async for token in callback.aiter():
                answer += token
            yield answer

        await task

    return StreamingResponse(chat_iterator(query, history),
                             media_type="text/event-stream")
