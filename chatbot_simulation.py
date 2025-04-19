import streamlit as st
from openai import OpenAI
import gspread
from google.oauth2 import service_account
import datetime
import re
import smtplib
from email.message import EmailMessage

# --- CONFIGURATION ---
OPENAI_API_KEY = st.secrets["openai_api_key"]
GOOGLE_SHEET_ID = st.secrets["google_sheet_id"]
MAILJET_API_KEY = st.secrets["mailjet_api_key"]
MAILJET_SECRET_KEY = st.secrets["mailjet_secret_key"]
EMAIL_FROM = st.secrets["email_from"]
EMAIL_TO = st.secrets["email_to"]
SMTP_SERVER = "in-v3.mailjet.com"
SMTP_PORT = 587
client = OpenAI(api_key=OPENAI_API_KEY)

# --- GOOGLE SHEETS AUTH ---
def get_gspread_client():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def clean_text(text, limit=10000):
    no_emojis = re.sub(r'[^\x00-\x7F]+', '', text)
    return no_emojis.replace("\n", " ⏎ ").replace("\r", "").strip()[:limit]

def send_email(subject, body):
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAILJET_API_KEY, MAILJET_SECRET_KEY)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"📩 Email failed: {e}")
        return False

# --- STREAMLIT APP ---
st.set_page_config(page_title="Chatter Training Bot", layout="wide")
st.title("💬 OnlyFans Fan Simulation Chatbot")
st.write("Practice chatting with a simulated fan. Your goal: flirt, upsell, and build trust.")

trainee_name = st.text_input("Enter your name before starting:")

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.chatter_count = 0

if not st.session_state.messages:
    st.session_state.messages.append({
        "role": "fan",
        "content": "Heyy 😏 just came across your page… not gonna lie, you’re looking dangerous 👀 what you up to rn?"
    })

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).markdown(msg["content"])

user_input = st.chat_input("Type your response...")

if user_input and st.session_state.chatter_count < 10:
    st.session_state.messages.append({"role": "chatter", "content": user_input})
    st.chat_message("chatter").markdown(user_input)
    st.session_state.chatter_count += 1

    formatted_messages = [
        {"role": "system", "content": (
            "You are playing the role of a FAN messaging an OnlyFans MODEL. "
            "You are a flirty, slightly pushy, emotionally curious American man in your mid 20s–30s. "
            "Your goal is to tease, flirt, challenge her prices, and sometimes be sweet or cheap. "
            "DO NOT act like the model or try to sell content."
        )}
    ]

    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "fan" else "user"
        formatted_messages.append({"role": role, "content": msg["content"]})

    response = client.chat.completions.create(
        model="gpt-4",
        messages=formatted_messages,
        temperature=0.9
    )

    fan_reply = response.choices[0].message.content
    st.session_state.messages.append({"role": "fan", "content": fan_reply})
    st.chat_message("fan").markdown(fan_reply)

# --- EVALUATION ---
def evaluate_and_email():
    conversation = "\n".join([
        f"{m['role'].capitalize()}: {m['content']}"
        for m in st.session_state.messages
    ])

    evaluation_prompt = f"""
You are a trainer at an OnlyFans agency. The following is a chat between a chatter and a fan.
Rate the chatter on the following out of 10:
- Natural tone & slang usage
- Progressive upselling
- Emotional connection
- Pricing confidence
- Handling objections

Then give 3 suggestions for improvement in a professional but helpful tone.

Conversation:
{conversation}
"""

    eval_response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": evaluation_prompt}],
        temperature=0.6
    )

    feedback = eval_response.choices[0].message.content
    scores = re.findall(r"(\d+)/10", feedback)
    final_score = sum([int(s) for s in scores]) * 2 if scores else 0
    feedback += f"\n\nFinal Overall Score: {final_score}/100"

    st.subheader("📊 Performance Feedback")
    st.write(feedback)

    # --- Log to Sheet ---
    try:
        gc = get_gspread_client()
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")
        row_data = [
            str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            trainee_name or "Unnamed",
            clean_text(conversation, 20000),
            clean_text(feedback, 10000)
        ]
        sheet.append_row(row_data, value_input_option="RAW")
        st.success("✅ Logged to Google Sheet!")
    except Exception as e:
        st.error(f"❌ Could not log to sheet: {e}")

    # --- Email Results ---
    if send_email(
        subject="💬 Chatbot Evaluation Results",
        body=f"Trainee: {trainee_name}\n\nFinal Score: {final_score}/100\n\nFeedback:\n{feedback}"
    ):
        st.success("📩 Email sent successfully to jordan@your-agency.ca")

if st.session_state.chatter_count >= 10:
    st.info("🔚 Chat ended after 10 chatter messages.")
    evaluate_and_email()
