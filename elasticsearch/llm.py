import openai
api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
model = "gpt-5"
base_url = "https://jeniya.cn/v1"



# api_key = "sk-3c00405e530947c0b54a068886d308d4"
# base_url = "https://api.deepseek.com/v1"
# model = "deepseek-chat"

client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "hi"},
            ]
        )
reply = response.choices[0].message.content
print(reply)


