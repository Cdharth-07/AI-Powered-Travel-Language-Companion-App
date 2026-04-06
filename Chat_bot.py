import streamlit as st
from openai import OpenAI
import base64
import os
import datetime
from io import BytesIO
from PIL import Image
from location_weather import get_location_and_weather, get_weather
from streamlit_js_eval import get_geolocation
from datetime import datetime
import json
import folium
from streamlit_folium import folium_static
import PyPDF2

# __import__('pysqlite3')
# import sys
# sys.modules['sqlite3']= sys.modules.pop('pysqlite3')

import chromadb
chroma_client = chromadb.PersistentClient(path="~/embeddings")

@st.dialog("Get Location")
def locat():
    if st.checkbox("Get my location"):
        get_coords()

@st.dialog("Take a Photo")
def cam():
    enable = st.checkbox("Enable camera")
    picture = st.camera_input("Take a picture", disabled=not enable)
    preprocess(picture)

@st.dialog("upload a file")
def upl():
    uploaded_file = st.file_uploader("Upload a photo", type=("jpg", "png"))
    preprocess(uploaded_file)

def get_coords():
    loc = get_geolocation()
    if loc:
        st.session_state.latitude = loc['coords']['latitude']
        st.session_state.longitude = loc['coords']['longitude']
        st.session_state.rerun_trigger = True # Trigger a rerun safely
        st.rerun()

def preprocess(picture):
    if picture:
        st.session_state.show_img = picture
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"image_{timestamp}.png"

        with open(file_path, "wb") as file:
            file.write(picture.getbuffer())

        with open(file_path, "rb") as image_file:
             st.session_state.img = base64.b64encode(image_file.read()).decode('utf-8')
        
        st.rerun()

def weather_location():
    # FIXED: Added the 3rd argument (client) required by your location_weather.py
    get_location_and_weather(st.session_state.latitude, st.session_state.longitude, st.session_state.client)

def add_coll(collection, text, filename, client):
    response = client.embeddings.create(
        input = text,
        model = "text-embedding-3-small"
    )
    embedding = response.data[0].embedding

    collection.add(
        documents=[text],
        ids = [filename],
        embeddings = embedding
    )

def read_pdf(file):
    reader = PyPDF2.PdfReader(file)
    text = ''
    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        text += page.extract_text()
    return text

def scan():
    if not os.path.exists('pdfs'):
        os.makedirs('pdfs')
    pdf_texts = {}
    for file_name in os.listdir('pdfs'):
        if file_name.endswith('.pdf'):
            file_path = os.path.join('pdfs', file_name)
            pdf_texts[file_name] = read_pdf(file_path)
            add_coll(st.session_state.Lab4_vectorDB, pdf_texts[file_name], file_name, st.session_state.client)

def get_city_attractions_info(query):
    response = st.session_state.client.embeddings.create(
    input=query,
    model="text-embedding-3-small")

    query_embedding = response.data[0].embedding

    results = st.session_state.Lab4_vectorDB.query(
                query_embeddings=[query_embedding],
                n_results=3
            )

    if results and len(results['documents'][0]) > 0:
        texts = []
        for i in range(len(results['documents'][0])):
            relevant_text = results['documents'][0][i]
            texts.append(relevant_text)
    else:
        texts = [" "]

    return texts

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather and local time",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and country, e.g. San Francisco, US",
                    },
                },
                "required": ["location"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_city_attractions_info",
            "description": "Takes a user-provided query and returns relevant information about tourist attractions, shopping places, and upcoming events in a specific city. Covers: Barcelona, Kyoto, New York City, Paris, Sydney, Tokyo",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user query for city info retrieval."
                    }
                },
                "required": ["query"]
            }
        }
    }]

# --- MAIN APP LOGIC ---

if "latitude" not in st.session_state:
    locat()
else:
    if 'client' not in st.session_state:
        st.session_state.client = OpenAI(api_key=st.secrets['openai_key'])

    if "location" not in st.session_state:
        # Fetch initial location and weather
        st.session_state.weather, st.session_state.local_time, st.session_state.location = get_location_and_weather(
            st.session_state.latitude, st.session_state.longitude, st.session_state.client
        )

    if 'Lab4_vectorDB' not in st.session_state:
        st.session_state.Lab4_vectorDB = chroma_client.get_or_create_collection('Lab4Collection')
        if 'scanned' not in st.session_state:
            scan()
            st.session_state.scanned = True

    if "messages" not in st.session_state:
        system_message = f'''
        You are a travel companion bot named Enten Nishiki. 
        Current Location: {st.session_state.location}. 
        Weather: {st.session_state.weather}. 
        Time: {st.session_state.local_time}.
        
        Greet the user, introduce yourself, and ask if they are exploring {st.session_state.location} or planning a trip elsewhere.
        If the user speaks a different language, reply in that language. 
        If asked to interpret, translate both ways until told to stop.
        Describe images provided by the user and translate any text within them.
        '''
        
        stream = st.session_state.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_message}]
        )

        st.session_state["messages"] = [
            {"role": "system", "content": system_message},
            {"role": "assistant", "content": stream.choices[0].message.content}
        ]

    # --- SIDEBAR UI ---
    st.sidebar.title(st.session_state.get("location", "Location Loading..."))
    
    # FIXED: Added Null Safety for weather icon
    if "weather" in st.session_state and st.session_state.weather and "weather" in st.session_state.weather:
        icon_id = st.session_state.weather["weather"][0]["icon"]
        st.sidebar.image(f"https://openweathermap.org/img/wn/{icon_id}@2x.png")
    else:
        st.sidebar.info("Weather data syncing...")

    if st.sidebar.button("Reset Location 🔃"):
        for key in ["location", "latitude", "longitude", "weather"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    if st.sidebar.button("Camera 📷"):
        cam()

    if st.sidebar.button("Upload files 📁"):
        upl()

    # MAP
    map_location = (st.session_state.latitude, st.session_state.longitude)
    m = folium.Map(location=map_location, zoom_start=15)
    folium.Marker(map_location, popup="You are here").add_to(m)
    with st.sidebar:
        folium_static(m, width=250, height=250)

    if "show_img" in st.session_state:
        st.sidebar.image(st.session_state.show_img)
        if st.sidebar.button("Clear ❌"):
            del st.session_state["img"]
            del st.session_state["show_img"]
            st.rerun()

    # --- CHAT INTERFACE ---
    for msg in st.session_state.messages:
        if msg["role"] != "system":
            with st.chat_message(msg["role"]):
                if isinstance(msg["content"], list):
                    st.write(msg["content"][0].get("text"))
                    if len(msg["content"]) > 1:
                        img_raw = base64.b64decode(msg["content"][1]["image_url"]["url"].split(",")[1])
                        st.image(img_raw, width=200)
                else:
                    st.write(msg["content"])

    if "first_message" not in st.session_state:
        st.session_state.first_message = st.session_state.messages[1]["content"]
        response = st.session_state.client.audio.speech.create(
            model="tts-1", voice="alloy", input=st.session_state.first_message
        )
        st.audio(response.content, autoplay=True)

    if audio_value := st.audio_input("How can I help?"):
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_value:
            st.session_state.last_audio = audio_value

            prompt = st.session_state.client.audio.transcriptions.create(
                model="whisper-1", file=audio_value, response_format="text"
            )

            # User message logic
            user_content = prompt
            if "img" in st.session_state:
                user_content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{st.session_state.img}"}}
                ]
                del st.session_state["img"]
                del st.session_state["show_img"]

            st.session_state.messages.append({"role": "user", "content": user_content})
            st.rerun() # Refresh to show user message immediately

    # Generate Response if last message is from user
    if st.session_state.messages[-1]["role"] == "user":
        with st.spinner("Thinking..."):
            stream = st.session_state.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=st.session_state.messages,
                tools=tools,
                tool_choice="auto",
            )

            response_message = stream.choices[0].message
            tool_calls = response_message.tool_calls

            if tool_calls:
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    if func_name == 'get_weather':
                        res = get_weather(args['location'])
                        st.session_state.messages.append({"role": "system", "content": f"Weather data: {res}"})
                    
                    if func_name == 'get_city_attractions_info':
                        res = get_city_attractions_info(args['query'])
                        st.session_state.messages.append({"role": "system", "content": f"RAG Data: {res}"})

                # Final completion after tool data is added
                final_stream = st.session_state.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=st.session_state.messages
                )
                answer = final_stream.choices[0].message.content
            else:
                answer = response_message.content

            # TTS and Output
            audio_res = st.session_state.client.audio.speech.create(
                model="tts-1", voice="alloy", input=answer
            )
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()