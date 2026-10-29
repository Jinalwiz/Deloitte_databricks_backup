#!pip install flask gitpython python-docx requests

import pandas as pd
from flask import Flask, request, jsonify, render_template_string, send_file
import logging
import re
import os
import git
from openai import OpenAI
from io import BytesIO
import base64
import requests as req
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

flask_app = Flask(__name__)

# ============ Configuration ============
GIT_URL = 'https://github.com/taruncheck/XMLtoSQL-Conversion.git'
LOCAL_REPO_DIR = '/tmp/XMLtoSQL-Conversion'
BRANCH = 'main'
PAT_TOKEN = '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'

# Store generated docs in memory
generated_docs = {}

# ============ XML to Tech Doc Functions ============

def get_databricks_client():
    """Initialize OpenAI client for Databricks."""
    return OpenAI(
        api_key=dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get(),
        base_url="https://enb-deloitte.cloud.databricks.com/serving-endpoints"
    )

def create_llm_system_message_for_logic():
    return (
        "You are an assistant that analyzes XML configuration files and creates detailed documentation.\n"
        "Your task is to analyze XML files and provide comprehensive field-level logic explanations.\n"
        "You will receive a main reporting view and all available XML files in the folder.\n"
        "Identify dependencies and trace logic through dependent views automatically.\n"
        "Focus on clarity, completeness, and technical accuracy.\n"
        "IMPORTANT: Respond ONLY with plain markdown text."
    )

def create_llm_system_message_for_design():
    return (
        "You are an assistant that creates visual design documentation from XML configuration files.\n"
        "Your task is to analyze XML files and create flow diagrams and design documentation.\n"
        "You will receive a main reporting view and all available XML files in the folder.\n"
        "Identify dependencies and show complete data flow through dependent views automatically.\n"
        "Focus on visual representation, data flow, and architectural clarity.\n"
        "Use mermaid syntax for diagrams enclosed in ```mermaid code blocks."
    )

def stream_gpt(client, system_message, prompt):
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(
        model="databricks-claude-sonnet-4-5",
        messages=messages,
        timeout=300
    )
    return response

def clone_or_pull_repo(git_url, local_dir, branch="main", pat_token=None):
    if pat_token:
        git_url = git_url.replace('https://', f'https://{pat_token}@')
    if not os.path.exists(local_dir):
        repo = git.Repo.clone_from(git_url, local_dir, branch=branch)
    else:
        repo = git.Repo(local_dir)
        repo.git.checkout(branch)
        repo.remotes.origin.pull()
    return repo

def load_all_xmls(xml_input_dir):
    all_xmls = {}
    for fname in os.listdir(xml_input_dir):
        if fname.lower().endswith('.xml'):
            xml_file_path = os.path.join(xml_input_dir, fname)
            try:
                with open(xml_file_path, 'r', encoding='utf-8') as f:
                    all_xmls[fname] = f.read()
            except Exception as e:
                print(f"Warning: Could not read {fname}: {str(e)}")
    return all_xmls

def build_all_xmls_context(all_xmls):
    context = "=== ALL AVAILABLE XML FILES ===\n\n"
    for filename, content in all_xmls.items():
        context += f"--- FILE: {filename} ---\n{content}\n\n"
    return context

def xml_file_to_logic_doc(client, reporting_view_name, all_xmls, system_message):
    all_xmls_context = build_all_xmls_context(all_xmls)
    prompt = (
        f"Your task: Analyze the reporting view '{reporting_view_name}' and create comprehensive logic documentation.\n\n"
        "**IMPORTANT INSTRUCTIONS**:\n"
        f"1. The main reporting view: **{reporting_view_name}**\n"
        "2. Automatically identify dependencies\n"
        "3. Trace logic through dependent views\n"
        "4. Document complete field lineage\n"
        f"{all_xmls_context}\n"
    )
    response = stream_gpt(client, system_message, prompt)
    return response

def xml_file_to_design_doc(client, reporting_view_name, all_xmls, system_message):
    all_xmls_context = build_all_xmls_context(all_xmls)
    prompt = (
        f"Your task: Analyze the reporting view '{reporting_view_name}' and create comprehensive design documentation.\n\n"
        "Create Mermaid flowcharts showing data flow.\n"
        f"{all_xmls_context}\n"
    )
    response = stream_gpt(client, system_message, prompt)
    return response

def extract_content_from_result(result):
    message_content = result.choices[0].message.content
    if isinstance(message_content, str):
        return message_content.strip()
    return str(message_content).strip()

def generate_tech_doc(view_name):
    """Generate technical documentation for a view."""
    try:
        client = get_databricks_client()
        
        # Clone/pull repository
        repo = clone_or_pull_repo(GIT_URL, LOCAL_REPO_DIR, BRANCH, PAT_TOKEN)
        repo.git.config('user.email', 'tarun8@deloitte.com')
        repo.git.config('user.name', 'taruncheck')
        
        xml_input_dir = os.path.join(LOCAL_REPO_DIR, 'XML Input')
        
        # Load XML files
        all_xmls = load_all_xmls(xml_input_dir)
        
        # Generate logic documentation
        logic_system_message = create_llm_system_message_for_logic()
        logic_result = xml_file_to_logic_doc(client, view_name, all_xmls, logic_system_message)
        logic_content = extract_content_from_result(logic_result)
        
        # Generate design documentation
        design_system_message = create_llm_system_message_for_design()
        design_result = xml_file_to_design_doc(client, view_name, all_xmls, design_system_message)
        design_content = extract_content_from_result(design_result)
        
        # Combine documents
        combined_content = f"# {view_name} - Technical Documentation\n\n"
        combined_content += "---\n\n# PART 1: LOGIC DOCUMENTATION\n\n"
        combined_content += logic_content
        combined_content += "\n\n---\n\n# PART 2: DESIGN DOCUMENTATION\n\n"
        combined_content += design_content
        
        # Store in memory
        generated_docs[view_name] = combined_content
        
        return {
            'success': True,
            'message': f'✅ Technical documentation generated for {view_name}!',
            'view_name': view_name,
            'doc_length': len(combined_content)
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'❌ Error generating documentation: {str(e)}'
        }

# ============ Flask Routes ============

@flask_app.route('/')
def hello_world():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>XML to Tech Doc Chatbot</title>
    <style>
        body { font-family: Arial, sans-serif; background: #383030; margin: 0; padding: 0; }
        #chat-container { width: 1000px; margin: 40px auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }
        #messages { height: 500px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; margin-bottom: 15px; background: #fafafa; border-radius: 4px; }
        .message { margin-bottom: 10px; padding: 8px; border-radius: 4px; }
        .user { color: #1976d2; background: #e3f2fd; }
        .bot { color: #388e3c; background: #e8f5e9; }
        .system { color: #f57c00; background: #fff3e0; font-style: italic; }
        #input-area { display: flex; gap: 8px; }
        #user-input { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        #send-btn { padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 4px; cursor: pointer; }
        #send-btn:hover { background: #1565c0; }
        .download-btn { display: inline-block; margin: 5px; padding: 8px 16px; background: #4caf50; color: white; text-decoration: none; border-radius: 4px; font-size: 14px; }
        .download-btn:hover { background: #45a049; }
        h2 { color: #333; margin-top: 0; }
        .help-text { color: #666; font-size: 14px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div id="chat-container">
        <h2>📄 XML to Technical Documentation Chatbot</h2>
        <div class="help-text">
            💡 Try: "Generate documentation for DLIFE__VRPT_OTIF_CALC" or "Create tech doc for [view_name]"
        </div>
        <div id="messages"></div>
        <div id="input-area">
            <input type="text" id="user-input" placeholder="Type your message or view name..." autocomplete="off" />
            <button id="send-btn">Send</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const userInput = document.getElementById('user-input');
        const sendBtn = document.getElementById('send-btn');

        function appendMessage(text, sender, isHtml = false) {
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message ' + sender;
            if (isHtml) {
                msgDiv.innerHTML = (sender === 'user' ? 'You: ' : sender === 'bot' ? 'Bot: ' : '') + text;
            } else {
                msgDiv.textContent = (sender === 'user' ? 'You: ' : sender === 'bot' ? 'Bot: ' : '') + text;
            }
            messagesDiv.appendChild(msgDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        async function sendMessage() {
            const message = userInput.value.trim();
            if (!message) return;
            appendMessage(message, 'user');
            userInput.value = '';
            
            // Show processing message
            appendMessage('Processing your request...', 'system');
            
            try {
                const response = await fetch('/converse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message })
                });
                if (!response.ok) throw new Error('Network response was not ok');
                const data = await response.json();
                
                // Remove processing message
                messagesDiv.removeChild(messagesDiv.lastChild);
                
                if (data.has_download) {
                    const downloadHtml = `${data.response}<br><br>
                        <a href="/download/${data.view_name}/md" class="download-btn">📄 Download Markdown</a>
                        <a href="/download/${data.view_name}/html" class="download-btn">🌐 Download HTML</a>`;
                    appendMessage(downloadHtml, 'bot', true);
                } else {
                    appendMessage(data.response, 'bot');
                }
            } catch (error) {
                messagesDiv.removeChild(messagesDiv.lastChild);
                appendMessage('Error: ' + error.message, 'bot');
            }
        }

        sendBtn.addEventListener('click', sendMessage);
        userInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') sendMessage();
        });
        
        // Welcome message
        appendMessage('Hello! I can generate technical documentation from XML files. Just tell me the view name!', 'bot');
    </script>
</body>
</html>
""")

@flask_app.route('/converse', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    
    # Check if user is requesting tech doc generation
    if is_tech_doc_request(user_message):
        view_name = extract_view_name(user_message)
        if view_name:
            result = generate_tech_doc(view_name)
            return jsonify({
                'response': result['message'],
                'has_download': result['success'],
                'view_name': view_name if result['success'] else None
            })
        else:
            return jsonify({
                'response': 'Please specify a view name. Example: "Generate documentation for DLIFE__VRPT_OTIF_CALC"',
                'has_download': False
            })
    else:
        # Regular chatbot response
        bot_response = get_bot_response(user_message)
        return jsonify({'response': bot_response, 'has_download': False})

@flask_app.route('/download/<view_name>/<format>')
def download_doc(view_name, format):
    """Download generated documentation."""
    if view_name not in generated_docs:
        return jsonify({'error': 'Documentation not found'}), 404
    
    content = generated_docs[view_name]
    
    if format == 'md':
        # Return markdown file
        buffer = BytesIO(content.encode('utf-8'))
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'{view_name}_TechDoc.md',
            mimetype='text/markdown'
        )
    
    elif format == 'html':
        # Convert to HTML
        html_content = markdown_to_html(content, f"{view_name} - Technical Documentation")
        buffer = BytesIO(html_content.encode('utf-8'))
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'{view_name}_TechDoc.html',
            mimetype='text/html'
        )
    
    return jsonify({'error': 'Invalid format'}), 400

def markdown_to_html(markdown_content, title):
    """Convert markdown to HTML with Mermaid support."""
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; }}
        h2 {{ color: #34495e; border-bottom: 2px solid #ecf0f1; }}
        code {{ background-color: #f8f9fa; padding: 2px 6px; }}
        .mermaid {{ background-color: white; padding: 20px; border: 1px solid #e0e0e0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; }}
        th {{ background-color: #3498db; color: white; }}
    </style>
    <script>mermaid.initialize({{ startOnLoad: true }});</script>
</head>
<body>{{CONTENT}}</body>
</html>"""
    
    html_content = markdown_content
    html_content = re.sub(r'```mermaid\s*\n(.*?)\n```', r'<div class="mermaid">\1</div>', html_content, flags=re.DOTALL)
    html_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_content)
    html_content = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_content)
    
    return html_template.replace('{{CONTENT}}', html_content)

def is_tech_doc_request(message):
    """Check if message is requesting tech doc generation."""
    keywords = ['generate', 'create', 'documentation', 'tech doc', 'document', 'analyze']
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in keywords)

def extract_view_name(message):
    """Extract view name from message."""
    # Look for patterns like "for VIEW_NAME" or "VIEW_NAME"
    patterns = [
        r'for\s+([A-Z_][A-Z0-9_]+)',
        r'view\s+([A-Z_][A-Z0-9_]+)',
        r'\b([A-Z_][A-Z0-9_]{5,})\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    
    return None

def get_bot_response(message):
    """Regular chatbot response using the existing endpoint."""
    client = OpenAI(
        api_key=dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get(),
        base_url="https://enb-deloitte.cloud.databricks.com/serving-endpoints"
    )

    response = client.responses.create(
        model="ka-db4d1506-endpoint",
        input=[{"role": "user", "content": message}]
    )
    return response.output[0].content[0].text

if __name__ == '__main__':
    flask_app.run(debug=True)
