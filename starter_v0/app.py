"""
AI News Digest - Streamlit UI
Polished chatbot interface with ChatGPT-style layout, streaming responses, 
source cards, and collapsible tool trace.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_shadcn_ui as ui

# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
TRANSCRIPTS_DIR = ROOT / "transcripts"

TOOL_COLORS = {
    "lookup": "#3B82F6",
    "fetch": "#10B981",
    "format": "#8B5CF6",
    "clarify": "#F59E0B",
    "timeline": "#EC4899",
    "social_search": "#06B6D4",
    "send": "#EF4444",
    "policy": "#6366F1",
    "papers": "#14B8A6",
    "paper_text": "#84CC16",
}

TOOL_ICONS = {
    "lookup": "Lookup",
    "fetch": "Fetch",
    "format": "Format",
    "clarify": "Clarify",
    "timeline": "Timeline",
    "social_search": "Social",
    "send": "Send",
    "policy": "Policy",
    "papers": "Papers",
    "paper_text": "Paper",
}

# ============================================================
# IMPORTS TỪ chat.py
# ============================================================

import sys
sys.path.insert(0, str(ROOT))

from env_loader import load_lab_env
from providers import make_provider
from providers.base import ToolCall
from tools import TOOL_FUNCTIONS, load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

load_lab_env(ROOT)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug.strip("_") or "run"


def json_text(value: Any, *, max_chars: int | None = None) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n...<truncated>"
    return text


def trim_history(history: list[dict[str, str]], window: int) -> list[dict[str, str]]:
    if window <= 0:
        return []
    return history[-window * 2:]


def execute_tool_call(call: ToolCall) -> dict[str, Any]:
    func = TOOL_FUNCTIONS.get(call.name)
    if not func:
        return {
            "tool": call.name,
            "args": call.args,
            "result": {"error": "unknown_tool", "message": f"No local implementation for {call.name}"},
        }
    try:
        result = func(**call.args)
    except Exception as exc:
        result = {"error": type(exc).__name__, "message": str(exc)}
    return {"tool": call.name, "args": call.args, "result": result}


def tool_results_message(events: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "TOOL_RESULTS_JSON:\n"
            f"{json_text(events, max_chars=24000)}\n\n"
            "Use only these tool results. If the user asked for a digest and the items are ready, "
            "call the formatting tool. Otherwise answer the user directly with cited sources when available."
        ),
    }


def assistant_tool_message(response_text: str | None, calls: list[ToolCall]) -> dict[str, str]:
    call_summary = [{"name": call.name, "args": call.args} for call in calls]
    content = response_text or "I will call the selected tool(s)."
    return {
        "role": "assistant",
        "content": f"{content}\n\nTOOL_CALLS_JSON:\n{json_text(call_summary)}",
    }


def run_model_tool_loop(
    *,
    provider: Any,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]],
    model: str | None,
    max_tool_rounds: int,
) -> dict[str, Any]:
    working_messages = list(messages)
    rounds: list[dict[str, Any]] = []
    all_tool_events: list[dict[str, Any]] = []

    for round_index in range(1, max_tool_rounds + 1):
        response = provider.complete(working_messages, tools, model=model, temperature=0.0)
        calls = response.tool_calls
        round_record: dict[str, Any] = {
            "round": round_index,
            "assistant_text": response.text,
            "tool_calls": [{"name": call.name, "args": call.args} for call in calls],
            "tool_results": [],
        }

        if not calls:
            rounds.append(round_record)
            return {
                "status": "answered",
                "assistant_text": response.text or "",
                "rounds": rounds,
                "tool_events": all_tool_events,
            }

        working_messages.append(assistant_tool_message(response.text, calls))
        non_clarification_events: list[dict[str, Any]] = []

        for call in calls:
            event = execute_tool_call(call)
            round_record["tool_results"].append(event)
            all_tool_events.append(event)

            result = event.get("result", {})
            if isinstance(result, dict) and result.get("awaiting_user"):
                question = result.get("question") or call.args.get("question") or "Ban bo sung them thong tin nhe."
                rounds.append(round_record)
                return {
                    "status": "waiting_for_user",
                    "assistant_text": question,
                    "rounds": rounds,
                    "tool_events": all_tool_events,
                }

            non_clarification_events.append(event)

        rounds.append(round_record)
        working_messages.append(tool_results_message(non_clarification_events))

    return {
        "status": "max_tool_rounds",
        "assistant_text": f"Stopped after {max_tool_rounds} tool rounds. Inspect the transcript for details.",
        "rounds": rounds,
        "tool_events": all_tool_events,
    }


def write_transcript(path: Path, transcript: dict[str, Any]) -> None:
    transcript["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_tool_color(tool_name: str) -> str:
    return TOOL_COLORS.get(tool_name.lower(), "#6B7280")


def get_tool_icon(tool_name: str) -> str:
    return TOOL_ICONS.get(tool_name.lower(), "Tool")


def load_transcripts() -> list[dict]:
    transcripts = []
    if TRANSCRIPTS_DIR.exists():
        for f in TRANSCRIPTS_DIR.glob("*.transcript.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                transcripts.append(data)
            except Exception:
                pass
    return sorted(transcripts, key=lambda x: x.get("created_at", ""), reverse=True)


# ============================================================
# UI COMPONENTS
# ============================================================

def render_sidebar():
    """Render ChatGPT-style sidebar with conversations and filters."""
    
    # Logo and title
    st.sidebar.markdown("""
    <div style="padding: 1rem 0; text-align: center; border-bottom: 1px solid #E2E8F0;">
        <h1 style="font-size: 1.25rem; margin: 0; color: #0A2540; font-weight: 700;">
            AI News Digest
        </h1>
        <p style="color: #64748B; margin: 0.25rem 0 0 0; font-size: 0.8rem;">
            Powered by Agent
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # New chat button
    if st.sidebar.button("+ New Chat", use_container_width=True, key="new_chat_btn"):
        st.session_state.messages = []
        st.session_state.history = []
        st.session_state.turn_index = 0
        st.session_state.transcript = None
        st.rerun()
    
    st.sidebar.divider()
    
    # Conversations section
    st.sidebar.subheader("Conversations")
    
    transcripts = load_transcripts()
    if transcripts:
        for t in transcripts[:10]:
            transcript_id = t.get("transcript_id", "Unknown")[:40]
            if st.sidebar.button(f"  {transcript_id}...", key=f"conv_{t.get('transcript_id')}"):
                st.session_state.selected_transcript = t
                st.rerun()
    else:
        st.sidebar.caption("No conversations yet")
    
    st.sidebar.divider()
    
    # Search filters
    st.sidebar.subheader("Filters")
    
    # Date range
    date_range = st.sidebar.selectbox(
        "Date Range",
        ["Today", "Last 7 days", "Last 30 days", "All time"],
        index=1
    )
    
    # Number of results (max 5 from Tavily free tier)
    num_results = st.sidebar.slider("So ket qua", 1, 5, 3)
    
    st.sidebar.divider()
    
    # Tool settings
    st.sidebar.subheader("Settings")
    
    show_tool_args = st.sidebar.checkbox(
        "Hien thi tool arguments",
        value=True,
        help="Hien thi chi tiet arguments khi goi tool"
    )
    
    # Provider info
    st.sidebar.divider()
    st.sidebar.markdown("""
    <div style="text-align: center; color: #94A3B8; font-size: 0.75rem; padding: 1rem 0;">
        Provider: <strong>OpenAI</strong><br>
        <span style="color: #10B981;">● Online</span>
    </div>
    """, unsafe_allow_html=True)
    
    return {
        "date_range": date_range,
        "num_results": num_results,
        "show_tool_args": show_tool_args,
    }


def render_source_cards(articles: list[dict]) -> None:
    """Render source cards using streamlit-shadcn-ui."""
    if not articles:
        return
    
    st.markdown("### Sources")
    
    for i, article in enumerate(articles):
        title = article.get("title", "Untitled")
        summary = article.get("summary", article.get("content", "")[:200] + "...")
        domain = article.get("domain", article.get("url", "Unknown")[:50])
        url = article.get("url", "")
        
        # Create card with shadcn-ui
        try:
            ui.card(
                title=title[:80] + ("..." if len(title) > 80 else ""),
                content=summary[:200] + ("..." if len(summary) > 200 else ""),
                description=f"Nguon: {domain}",
                key=f"source_card_{i}"
            ).render()
            
            if url and st.button("Doc bai viet", key=f"read_btn_{i}"):
                st.markdown(f"[Mo link]({url})")
        except Exception:
            # Fallback to native st elements
            with st.container():
                st.markdown(f"**{title}**")
                st.caption(f"Nguon: {domain}")
                st.write(summary[:200] + "...")
                if url:
                    st.markdown(f"[Doc bai viet]({url})")
                st.divider()


def render_tool_trace_collapsible(tool_events: list[dict], show_args: bool) -> None:
    """Render collapsible tool trace panel."""
    if not tool_events:
        return
    
    tool_count = len(tool_events)
    status_text = f"Agent execution · {tool_count} tools"
    
    with st.expander(status_text, expanded=False):
        for i, event in enumerate(tool_events):
            tool_name = event.get("tool", "unknown")
            args = event.get("args", {})
            result = event.get("result", {})
            color = get_tool_color(tool_name)
            
            # Tool name badge
            st.markdown(f"""
            <div style="
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                background: {color}15;
                border: 1px solid {color};
                border-radius: 6px;
                padding: 0.35rem 0.75rem;
                margin-bottom: 0.5rem;
            ">
                <span style="font-weight: 600; color: {color}; font-size: 0.8rem;">
                    {tool_name.upper()}
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            # Check for errors
            if isinstance(result, dict) and result.get("error"):
                st.error(f"Loi: {result.get('error')} - {result.get('message', '')}")
            
            # Arguments
            if args and show_args:
                with st.expander("Arguments", expanded=False):
                    st.json(args)
            
            # Result preview
            if isinstance(result, dict):
                # Show first few keys
                preview = {k: v for k, v in list(result.items())[:3]}
                preview_str = json.dumps(preview, default=str)[:300]
                st.caption(f"Result: {preview_str}...")
            else:
                st.caption(f"Result: {str(result)[:100]}...")
            
            if i < len(tool_events) - 1:
                st.markdown("---")


def render_artifact_version_badge() -> None:
    """Render current artifact version badge."""
    try:
        artifact_version = build_artifact_version("v3", ARTIFACTS_DIR / "system_prompt.md", ARTIFACTS_DIR / "tools.yaml")
        version_info = artifact_version_dict(artifact_version)
        
        st.markdown(f"""
        <div style="
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 0.25rem 0.75rem;
            font-size: 0.75rem;
            color: #64748B;
        ">
            <span style="color: #0A2540; font-weight: 600;">Agent v3</span>
            <span>·</span>
            <span style="font-family: monospace;">{version_info.get('version', 'N/A')[:8]}</span>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        pass


def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "history" not in st.session_state:
        st.session_state.history = []
    if "turn_index" not in st.session_state:
        st.session_state.turn_index = 0
    if "transcript" not in st.session_state:
        st.session_state.transcript = None
    if "provider" not in st.session_state:
        st.session_state.provider = None


def handle_user_input(prompt: str, settings: dict) -> None:
    """Handle user input and run agent."""
    st.session_state.turn_index += 1
    user_text = prompt
    
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": user_text})
    
    with st.chat_message("user"):
        st.markdown(user_text)
    
    # Initialize provider if needed
    if st.session_state.provider is None:
        try:
            st.session_state.provider = make_provider("openai")
            st.session_state.tool_declarations = load_tool_declarations(ARTIFACTS_DIR / "tools.yaml")
            st.session_state.openai_tools = to_openai_tools(st.session_state.tool_declarations)
            st.session_state.system_prompt = (ARTIFACTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
        except Exception as e:
            st.error(f"Loi khoi tao: {e}")
            return
    
    # Build messages
    messages = [
        {"role": "system", "content": st.session_state.system_prompt},
        *trim_history(st.session_state.history, 5),
        {"role": "user", "content": user_text},
    ]
    
    # Create transcript record
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = f"chat_{safe_slug(user_text[:20])}_{timestamp}"
    transcript_path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    
    turn_record = {
        "turn_index": st.session_state.turn_index,
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }
    
    # Run agent with status
    result = None
    with st.status("Dang xu ly...", expanded=True) as status:
        try:
            result = run_model_tool_loop(
                provider=st.session_state.provider,
                messages=messages,
                tools=st.session_state.openai_tools,
                model=None,
                max_tool_rounds=4,  # Fixed max rounds
            )
            
            turn_record.update(result)
            assistant_text = result.get("assistant_text", "")
            
            # Update session state
            st.session_state.history.append({"role": "user", "content": user_text})
            st.session_state.history.append({"role": "assistant", "content": assistant_text})
            
            # Save transcript
            turn_record["ended_at"] = now_iso()
            transcript = {
                "transcript_id": transcript_id,
                **artifact_version_dict(build_artifact_version("v3", ARTIFACTS_DIR / "system_prompt.md", ARTIFACTS_DIR / "tools.yaml")),
                "provider": "openai",
                "model": getattr(st.session_state.provider, "default_model", "N/A"),
                "created_at": now_iso(),
                "turns": [turn_record],
            }
            write_transcript(transcript_path, transcript)
            
            status.update(label="Hoan tat!", state="complete", expanded=False)
            
        except Exception as e:
            turn_record.update({
                "status": "provider_error",
                "error": f"{type(e).__name__}: {str(e)}",
            })
            assistant_text = f"Da xay ra loi: {str(e)}"
            status.update(label="Loi!", state="error")
    
    # Display assistant response
    with st.chat_message("assistant"):
        st.markdown(assistant_text)
        st.session_state.messages.append({"role": "assistant", "content": assistant_text})
        
        # Show tool trace
        tool_events = []
        if result and result.get("tool_events"):
            tool_events = result.get("tool_events", [])
            render_tool_trace_collapsible(tool_events, settings.get("show_tool_args", True))
        
        # Show source cards if available
        articles = []
        for event in tool_events:
            result_data = event.get("result", {})
            if isinstance(result_data, dict) and "articles" in result_data:
                articles.extend(result_data["articles"])
            elif isinstance(result_data, dict) and "results" in result_data:
                articles.extend(result_data["results"])
        
        if articles:
            render_source_cards(articles[:settings.get("num_results", 5)])


def render_empty_state():
    """Render empty state when no messages."""
    st.markdown("""
    <div style="
        text-align: center;
        padding: 3rem 1rem;
        color: #64748B;
    ">
        <h2 style="color: #0A2540; font-weight: 600;">Xin chào!</h2>
        <p>Bạn muốn tìm kiếm tin gì hôm nay?</p>
        <p style="font-size: 0.875rem;">
            Hãy nhập câu hỏi vào ô chat phía dưới
        </p>
    </div>
    """, unsafe_allow_html=True)


def render_header():
    """Render main header."""
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.title("AI News Digest")
    
    with col2:
        render_artifact_version_badge()
    
    with col3:
        if st.session_state.transcript:
            transcript_id = st.session_state.transcript.get("transcript_id", "")[:20]
            st.caption(f"Session: {transcript_id}...")


# ============================================================
# MAIN APP
# ============================================================

def main():
    st.set_page_config(
        page_title="AI News Digest",
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS - Editorial Technology News Aesthetic
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Main background */
    .stApp {
        background: #FFFFFF;
    }
    
    /* Main content area */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 5rem;
    }
    
    /* Typography */
    html, body, .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: #1E293B;
    }
    
    h1, h2, h3, h4 {
        font-family: 'Inter', sans-serif;
        color: #0A2540;
        font-weight: 700;
    }
    
    /* Clean scrollbar */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #F1F5F9;
    }
    ::-webkit-scrollbar-thumb {
        background: #CBD5E1;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #94A3B8;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: #F8FAFC;
        border-right: 1px solid #E2E8F0;
    }
    
    /* Chat input */
    .stChatInput {
        position: fixed;
        bottom: 0;
        background: white;
        padding: 1rem;
        border-top: 1px solid #E2E8F0;
    }
    
    /* Chat messages - clean style */
    [data-testid="stChatMessage"] {
        padding: 0.5rem 0;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: #F1F5F9;
        padding: 4px;
        border-radius: 8px;
        border: none;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        color: #64748B;
        font-weight: 500;
        border: none;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: #FFFFFF;
        color: #0A2540;
    }
    
    .stTabs [aria-selected="true"] {
        background: #FFFFFF !important;
        color: #0A2540 !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        font-weight: 600;
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        color: #1E293B;
        font-weight: 500;
    }
    
    .streamlit-expanderHeader:hover {
        background: #F1F5F9;
    }
    
    /* Buttons - clean primary */
    .stButton > button {
        background: #0A2540;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: background 0.2s;
    }
    
    .stButton > button:hover {
        background: #1E3A5F;
    }
    
    /* Input fields */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div {
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        background: #FFFFFF;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #0A2540;
        box-shadow: 0 0 0 2px rgba(10,37,64,0.1);
    }
    
    /* Slider */
    .stSlider > div > div > div {
        background: #E2E8F0;
    }
    
    .stSlider [data-testid="stThumbValue"] {
        color: #0A2540;
        font-weight: 600;
    }
    
    /* Status box */
    .stStatus {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
    }
    
    /* Checkbox */
    .stCheckbox > label {
        color: #1E293B;
        font-weight: 500;
    }
    
    /* Cards */
    [data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }
    
    /* Alert boxes */
    .stAlert {
        border-radius: 8px;
        border: none;
    }
    
    /* JSON display */
    .stJson {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
    }
    
    /* Dividers */
    hr {
        border: none;
        border-top: 1px solid #E2E8F0;
    }
    
    /* Caption text */
    .stCaption {
        color: #64748B;
        font-size: 0.75rem;
    }
    
    /* Subheaders */
    .stSubheader {
        color: #0A2540;
        font-weight: 600;
    }
    
    /* Spinner */
    .stSpinner > div {
        border-color: #0A2540;
    }
    
    /* Success/Info/Error */
    .stSuccess {
        background: #ECFDF5;
        color: #065F46;
    }
    
    .stInfo {
        background: #EFF6FF;
        color: #1E40AF;
    }
    
    .stError {
        background: #FEF2F2;
        color: #991B1B;
    }
    
    /* Badge style for version */
    .version-badge {
        display: inline-block;
        background: #0A2540;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.875rem;
    }
    
    /* Source cards */
    .source-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    init_session_state()
    
    # Render sidebar and get settings
    settings = render_sidebar()
    
    # Main content area
    render_header()
    
    # Tabs for Chat and Transcripts
    tab1, tab2 = st.tabs(["Chat", "Transcripts"])
    
    with tab1:
        # Display chat messages
        if st.session_state.messages:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        else:
            render_empty_state()
        
        # Chat input
        if prompt := st.chat_input("Nhap yeu cau tim kiem..."):
            handle_user_input(prompt, settings)
    
    with tab2:
        render_transcripts_tab(settings)


def render_transcripts_tab(settings: dict) -> None:
    """Render transcripts list tab."""
    transcripts = load_transcripts()
    
    if not transcripts:
        st.info("Chua co transcript nao. Hay chat de tao transcript!")
        return
    
    st.success(f"Tim thay {len(transcripts)} transcript(s)")
    
    for i, transcript in enumerate(transcripts):
        transcript_id = transcript.get("transcript_id", "Unknown")[:50]
        
        with st.expander(f"Transcript: {transcript_id}...", expanded=False):
            # Version info
            st.markdown(f"""
            **Version:** {transcript.get('version', 'N/A')} | 
            **Provider:** {transcript.get('provider', 'N/A')} | 
            **Model:** {transcript.get('model', 'N/A')}
            """)
            
            # Artifact version
            artifact_ver = transcript.get('artifact_version', 'N/A')
            st.caption(f"Artifact: {artifact_ver[:40]}...")
            
            # Turns
            turns = transcript.get("turns", [])
            if turns:
                st.markdown(f"**{len(turns)} turn(s)**")
                
                for j, turn in enumerate(turns):
                    with st.expander(f"Turn {j+1}: {turn.get('user', '')[:50]}...", expanded=False):
                        st.markdown(f"**User:** {turn.get('user', '')}")
                        
                        assistant_text = turn.get("assistant_text", "")
                        if assistant_text:
                            st.markdown(f"**Assistant:** {assistant_text}")
                        
                        # Status
                        status = turn.get("status", "unknown")
                        status_colors = {
                            "answered": "#10B981",
                            "waiting_for_user": "#F59E0B",
                            "max_tool_rounds": "#EF4444",
                            "provider_error": "#EF4444",
                        }
                        color = status_colors.get(status, "#64748B")
                        st.markdown(f"**Status:** :{color}[{status}]")
                        
                        # Tool events
                        tool_events = turn.get("tool_events", [])
                        if tool_events:
                            render_tool_trace_collapsible(tool_events, settings.get("show_tool_args", True))


if __name__ == "__main__":
    main()
