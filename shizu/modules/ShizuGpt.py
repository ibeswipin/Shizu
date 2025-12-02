# Shizu Copyright (C) 2023-2024  AmoreForever

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import re
import requests

from pyrogram import types, Client
from .. import loader, utils

# https://raw.githubusercontent.com/MoriSummerz/ftg-mods/main/chatgpt.py


@loader.module("ShizuGpt", "hikamoru", 1.0)
class ShizuGpt(loader.Module):
    """ChatGPT AI API interaction"""

    strings = {}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "GPT_KEY", None, lambda m: self.strings("cfg_doc"),
            "GPT_MODEL", "gpt-4o-mini", lambda m: self.strings("cfg_model_doc"),
            "GPT_TEMPERATURE", 0.7, lambda m: self.strings("cfg_temp_doc"),
        )
        self._conversation_history = {} 

    async def _make_request(
        self,
        method: str,
        url: str,
        headers: dict,
        data: dict,
    ) -> dict:
        """
        Makes an asynchronous HTTP request using the specified method, URL,
        headers, and data.

        Parameters:
            method (str): The HTTP method to use for the request.
            url (str): The URL to send the request to.
            headers (dict): The headers to include in the request.
            data (dict): The JSON data to include in the request body.

        Returns:
            dict: The JSON response from the server.
        """
        resp = await utils.run_sync(
            requests.request,
            method,
            url,
            headers=headers,
            json=data,
        )
        return resp.json()

    def _process_code_tags(self, text: str) -> str:
        """Improved code block processing with language support"""
        text = re.sub(
            r"```(\w+)?\n?(.*?)```",
            r"<code>\2</code>",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text
    
    def _get_system_prompt(self) -> str:
        """Enhanced system prompt for better responses"""
        return """You are a helpful, intelligent, and creative AI assistant. 
- Provide clear, detailed, and well-structured answers
- Use proper formatting with code blocks when sharing code
- Be concise but comprehensive
- Adapt your communication style to the user's needs
- If asked to explain code, provide thorough explanations
- For creative tasks, be imaginative and engaging
- Always prioritize accuracy and helpfulness"""

    async def _get_chat_completion(
        self, prompt: str, token: str, chat_id: int = None
    ) -> str:
        """Enhanced chat completion with conversation history and better prompts"""
        model = self.config.get("GPT_MODEL", "gpt-4o-mini")
        temperature = float(self.config.get("GPT_TEMPERATURE", 0.7))
        
        messages = [{"role": "system", "content": self._get_system_prompt()}]
        
        if chat_id and chat_id in self._conversation_history:
            messages.extend(self._conversation_history[chat_id][-10:])  
        
        
        messages.append({"role": "user", "content": prompt})
        
        resp = await self._make_request(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            data={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 2000,
            },
        )
        
        if resp.get("error", None):
            return f"🚫 {resp['error']['message']}"

        assistant_message = resp["choices"][0]["message"]["content"]
        
        if chat_id:
            if chat_id not in self._conversation_history:
                self._conversation_history[chat_id] = []
            self._conversation_history[chat_id].append({"role": "user", "content": prompt})
            self._conversation_history[chat_id].append({"role": "assistant", "content": assistant_message})
            if len(self._conversation_history[chat_id]) > 20:
                self._conversation_history[chat_id] = self._conversation_history[chat_id][-20:]

        return assistant_message

    @loader.command()
    async def gpt(self, app: Client, message: types.Message):
        """Ask question to GPT"""
        args = message.get_args_raw()

        if not args:
            return await message.answer(self.strings("what_ask"))

        token = self.config["GPT_KEY"]
        if not token:
            return await message.answer(self.strings("no_token"))
        
        chat_id = message.chat.id if message.chat else None
        
        msg = await message.answer(self.strings("pending").format(args))
        answer = await self._get_chat_completion(args, token, chat_id)
        await utils.answer(
            msg, self.strings("answer").format(args, self._process_code_tags(answer))
        )
    
    @loader.command()
    async def gptclear(self, app: Client, message: types.Message):
        """Clear conversation history"""
        chat_id = message.chat.id if message.chat else None
        if chat_id and chat_id in self._conversation_history:
            del self._conversation_history[chat_id]
            await message.answer(self.strings("clear_success"))
        else:
            await message.answer(self.strings("clear_empty"))
