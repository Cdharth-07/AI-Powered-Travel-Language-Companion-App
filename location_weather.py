import streamlit as st
import json
from openai import OpenAI
from geopy.geocoders import Nominatim
import requests
from datetime import datetime

geolocator = Nominatim(user_agent="location_finder")

def get_location_and_weather(latitude, longitude, client):
    geolocator = Nominatim(user_agent="location_finder")
    
    try:
        location_obj = geolocator.reverse((latitude, longitude), language="en")
        address = location_obj.raw.get('address', {})
        city = address.get('city', address.get('town', address.get('village', '')))
        state = address.get('state', '')
        country = address.get('country', '')
        
        raw_location = f"{city}, {state}, {country}"

        coor_message = """
        Format the location for OpenWeatherMap API. 
        Example: "City of Syracuse, New York, United States" -> "Syracuse, US".
        Return ONLY the formatted string.
        """

        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": coor_message},
                      {"role": "user", "content": raw_location}]
        )

        formatted_location = stream.choices[0].message.content

        data, local_time = get_weather(formatted_location)
        
        return data, local_time, formatted_location
    except Exception as e:
        st.error(f"Location Error: {e}")
        return None, None, "Unknown Location"

def get_weather(formatted_location):
    urlbase = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": formatted_location,
        "appid": st.secrets['weather_key'],
        "units": "metric"
    }

    response = requests.get(urlbase, params=params)
    data = response.json()

    # Check if the API returned a success code (200)
    if response.status_code != 200:
        error_msg = data.get('message', 'Unknown API Error')
        st.warning(f"Weather API Warning: {error_msg}. Check if your OpenWeather key is active (30-60 min delay).")
        return data, datetime.now() 

    # Only access 'dt' if the request was successful
    utc_timestamp = data.get('dt', int(datetime.now().timestamp()))
    offset_seconds = data.get('timezone', 0)
    local_timestamp = utc_timestamp + offset_seconds
    local_time = datetime.fromtimestamp(local_timestamp)

    return data, local_time
