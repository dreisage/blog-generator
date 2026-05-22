from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Credentials from .env file
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

class BlogPost(BaseModel):
    topic: str

# Root route - serve index.html
@app.get("/")
async def serve_frontend():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>index.html not found</h1>", status_code=404)

# Generate blog endpoint
@app.post("/generate_blog/")
async def generate_blog(post: BlogPost):
    try:
        print(f"📝 Generating blog about: {post.topic}")
        
        # Generate blog using OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional blog writer. Write a detailed, engaging blog post."},
                {"role": "user", "content": f"Write a comprehensive blog post about: {post.topic}. Include a catchy title first, then the full article. Make it at least 400 words."}
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        generated_content = response.choices[0].message.content
        
        # Extract title and content
        lines = generated_content.strip().split('\n')
        title = lines[0].replace('#', '').strip()
        content = '\n'.join(lines[1:]).strip()
        
        if not title:
            title = post.topic
        
        print(f"✅ Blog generated: {title}")
        
        # Save to Supabase
        supabase_headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY
        }
        
        supabase_data = {
            "topic": post.topic,
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat()
        }
        
        supabase_response = requests.post(
            f"{SUPABASE_URL}/rest/v1/blog_posts",
            headers=supabase_headers,
            json=supabase_data
        )
        
        if supabase_response.status_code in [200, 201]:
            print(f"✅ Saved to Supabase")
        else:
            print(f"⚠️ Supabase error: {supabase_response.text}")
        
        # Send to Discord as HTML file attachment
        await send_to_discord(title, content)
        
        return {
            "success": True,
            "title": title, 
            "content": content,
            "topic": post.topic
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Get all posts endpoint
@app.get("/get_posts/")
async def get_posts():
    try:
        supabase_headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/blog_posts?select=*&order=created_at.desc",
            headers=supabase_headers
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Error fetching posts")
        
        posts = response.json()
        print(f"📚 Retrieved {len(posts)} posts from Supabase")
        return posts
        
    except Exception as e:
        print(f"❌ Error fetching posts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Discord webhook function
async def send_to_discord(title: str, content: str):
    try:
        if not DISCORD_WEBHOOK:
            print("⚠️ No Discord webhook configured")
            return False
            
        # Create summary (first 200 characters)
        summary = content[:200].strip().replace('\n', ' ') + "..."
        
        # Create HTML file with proper formatting
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2rem;
            margin-bottom: 10px;
        }}
        .header .date {{
            opacity: 0.9;
            font-size: 0.9rem;
        }}
        .content {{
            padding: 40px;
            line-height: 1.8;
            color: #333;
        }}
        .content p {{
            margin-bottom: 20px;
        }}
        .content h2 {{
            color: #667eea;
            margin: 30px 0 15px 0;
        }}
        .footer {{
            background: #f7f7f7;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 0.8rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="date">{datetime.now().strftime("%B %d, %Y")}</div>
        </div>
        <div class="content">
            {content.replace(chr(10), '<br>').replace('**', '<strong>').replace('</strong>', '</strong>')}
        </div>
        <div class="footer">
            🤖 Generated by AI Blog Generator
        </div>
    </div>
</body>
</html>"""
        
        # Prepare multipart form data for Discord
        files = {
            'file': (f'{title[:50].replace(" ", "_").replace("/", "_")}.html', html_content, 'text/html')
        }
        data = {
            'content': f'**📝 {title}**\n\n{summary}'
        }
        
        # Send to Discord
        response = requests.post(DISCORD_WEBHOOK, data=data, files=files)
        
        if response.status_code == 204:
            print("✅ Blog sent to Discord successfully!")
            return True
        else:
            print(f"⚠️ Discord error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Discord exception: {str(e)}")
        return False

# Test Discord endpoint
@app.get("/test-discord/")
async def test_discord():
    try:
        if not DISCORD_WEBHOOK:
            return {"error": "No Discord webhook configured in .env file"}
        
        response = requests.post(
            DISCORD_WEBHOOK, 
            json={"content": "✅ Discord webhook is working! Blog generator is online."}
        )
        
        if response.status_code == 204:
            return {"status": "success", "message": "Test message sent to Discord!"}
        else:
            return {"status": "error", "code": response.status_code, "message": response.text}
            
    except Exception as e:
        return {"error": str(e)}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": "configured" if OPENAI_API_KEY else "missing",
            "supabase": "configured" if SUPABASE_URL and SUPABASE_KEY else "missing",
            "discord": "configured" if DISCORD_WEBHOOK else "missing"
        }
    }