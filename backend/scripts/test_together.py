import asyncio
import os
from dotenv import load_dotenv
from together import AsyncTogether

load_dotenv()

async def test_llm():
    api_key = os.getenv("TOGETHER_API_KEY")
    client = AsyncTogether(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10
        )
        print("Success:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_llm())
