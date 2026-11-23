# soundsafe

A voice assistant that knows **who is speaking**, alongside **who can hear**, and changes the response depending on these two factors. Friends get rough answers, strangers get nothing, and people that are calling are checked against their voice, not just their number/called id. Safesound never reveals that some information is being held back.

Speaker recognition model and STT run locally, never leaves your machine.

#Run it
You need: Python 3.11 or 3.12, supported browser, microphone, internet for first connection (downloads ~200MB of speech models)

```bash
git clone https://github.com/pigeoncoder1/safesound.git
cd safesound
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python -m safesound.server
```

Open https://127.0.0.1:8000 in a tab:
1. Set up your voice
2. Press start mic.
3. Click "How to try it" (top right) for example prompts.

It works with regex for prompts, but adding your anthropic key to the .env file lets it understand non-natural phrasing. Adding a .env file and filling in your anthropic key **is advised**. For testing, I have submitted my own key with a limit in the form alongside my submission.

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here

The AI only ever sees the transcript text, never your messages, location or calendar.

Optionally, Safesound also supports Llama through Ollama if you want to run the AI model locally:
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

Run tests using: ```python -m pytest```


















during testing, trying to find the ideal threshold for recognising the speaker, these are the results.

<img width="960" height="540" alt="image" src="https://github.com/user-attachments/assets/5aa28de0-5095-4a72-a479-3c115d2f7523" />
<img width="960" height="540" alt="image" src="https://github.com/user-attachments/assets/73d5b18e-7089-43bf-b257-46d8654076aa" />
<img width="960" height="540" alt="image" src="https://github.com/user-attachments/assets/81d6823b-de62-42f9-a87b-fad17e73215e" />
<img width="960" height="540" alt="image" src="https://github.com/user-attachments/assets/f6da5e5c-f7b5-4fbc-84f2-98eabbed9d79" />


This is a quick mock-up for live testing of the similarity scores:
<img width="480" height="862" alt="image" src="https://github.com/user-attachments/assets/625d4591-e2bc-4d72-856a-fa7e513980f0" />
