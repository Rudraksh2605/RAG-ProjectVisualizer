import streamlit as st

def load_css():
    """Injects custom CSS for a premium, modern dark-themed UI."""
    st.markdown("""
    <style>
        /* ═══════════════════════════════════════════════
           Google Fonts Import
           ═══════════════════════════════════════════════ */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

        /* ═══════════════════════════════════════════════
           Global Overrides
           ═══════════════════════════════════════════════ */
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        }
        
        .stApp {
            background: linear-gradient(160deg, #0a0a14 0%, #0f0f1e 30%, #111128 60%, #0d0d1a 100%);
        }

        /* Subtle animated noise grain overlay */
        .stApp::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.02'/%3E%3C/svg%3E");
            pointer-events: none;
            z-index: 0;
        }

        /* ═══════════════════════════════════════════════
           Scrollbar Styling
           ═══════════════════════════════════════════════ */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #3b3b5c; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #8B5CF6; }

        /* ═══════════════════════════════════════════════
           Sidebar Styling
           ═══════════════════════════════════════════════ */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d0d1a 0%, #12122a 50%, #0f0f20 100%) !important;
            border-right: 1px solid rgba(139, 92, 246, 0.15) !important;
        }
        
        section[data-testid="stSidebar"] .stMarkdown h1 {
            background: linear-gradient(135deg, #8B5CF6 0%, #06B6D4 50%, #8B5CF6 100%);
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradient-shift 4s ease infinite;
            font-weight: 800;
            letter-spacing: -0.03em;
        }

        @keyframes gradient-shift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }

        /* ═══════════════════════════════════════════════
           Tab Styling
           ═══════════════════════════════════════════════ */
        .stTabs [data-baseweb="tab-list"] {
            background: rgba(15, 15, 30, 0.6);
            backdrop-filter: blur(12px);
            border-radius: 14px;
            border: 1px solid rgba(139, 92, 246, 0.12);
            padding: 4px;
            gap: 4px;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            padding: 10px 18px;
            font-weight: 500;
            font-size: 0.85rem;
            color: #94A3B8;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: none !important;
            background: transparent !important;
        }

        .stTabs [data-baseweb="tab"]:hover {
            color: #E2E8F0;
            background: rgba(139, 92, 246, 0.08) !important;
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(6, 182, 212, 0.15)) !important;
            color: #fff !important;
            font-weight: 600;
            box-shadow: 0 0 20px rgba(139, 92, 246, 0.15);
        }
        
        .stTabs [data-baseweb="tab-highlight"] {
            display: none !important;
        }

        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }

        /* ═══════════════════════════════════════════════
           Stat Cards — Glassmorphism
           ═══════════════════════════════════════════════ */
        .stat-card {
            background: linear-gradient(135deg, rgba(26, 26, 50, 0.8) 0%, rgba(30, 30, 60, 0.6) 100%);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(139, 92, 246, 0.15);
            border-radius: 16px;
            padding: 24px 20px;
            text-align: center;
            margin-bottom: 10px;
            transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: -50%; right: -50%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.5), transparent);
        }
        .stat-card:hover {
            border-color: rgba(139, 92, 246, 0.35);
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(139, 92, 246, 0.12);
        }
        .stat-card h2 {
            font-size: 2.2rem;
            margin: 0;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #8B5CF6 0%, #06B6D4 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stat-card p {
            color: #64748B;
            margin: 6px 0 0 0;
            font-size: 0.8rem;
            font-weight: 500;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* ═══════════════════════════════════════════════
           Status Badges
           ═══════════════════════════════════════════════ */
        .badge-ok {
            color: #4ADE80;
            font-weight: 600;
            font-size: 0.9rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            background: rgba(74, 222, 128, 0.08);
            border-radius: 8px;
            border: 1px solid rgba(74, 222, 128, 0.2);
        }
        .badge-err {
            color: #F87171;
            font-weight: 600;
            font-size: 0.9rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            background: rgba(248, 113, 113, 0.08);
            border-radius: 8px;
            border: 1px solid rgba(248, 113, 113, 0.2);
        }

        /* ═══════════════════════════════════════════════
           Section Divider
           ═══════════════════════════════════════════════ */
        .section-divider {
            border: none;
            border-top: 1px solid rgba(139, 92, 246, 0.1);
            margin: 2rem 0;
            position: relative;
        }

        /* ═══════════════════════════════════════════════
           Diagram Result Card
           ═══════════════════════════════════════════════ */
        .diagram-card {
            background: linear-gradient(135deg, rgba(15, 15, 35, 0.9) 0%, rgba(26, 26, 50, 0.7) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(139, 92, 246, 0.15);
            border-radius: 14px;
            padding: 18px 22px;
            margin-bottom: 14px;
            transition: all 0.3s ease;
        }
        .diagram-card:hover {
            border-color: rgba(139, 92, 246, 0.3);
            box-shadow: 0 4px 20px rgba(139, 92, 246, 0.1);
        }
        .diagram-card h4 {
            color: #A78BFA;
            margin: 0;
            font-weight: 600;
            font-size: 1.05rem;
            letter-spacing: -0.01em;
        }

        /* ═══════════════════════════════════════════════
           Security Severity Badges
           ═══════════════════════════════════════════════ */
        .sev-badge {
            display: inline-flex;
            align-items: center;
            padding: 3px 12px;
            border-radius: 8px;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .sev-critical { background: linear-gradient(135deg, #DC2626, #EF4444); color: #fff; box-shadow: 0 2px 8px rgba(220, 38, 38, 0.3); }
        .sev-high { background: linear-gradient(135deg, #EA580C, #F97316); color: #fff; box-shadow: 0 2px 8px rgba(234, 88, 12, 0.3); }
        .sev-medium { background: linear-gradient(135deg, #D97706, #F59E0B); color: #fff; box-shadow: 0 2px 8px rgba(217, 119, 6, 0.3); }
        .sev-low { background: linear-gradient(135deg, #2563EB, #3B82F6); color: #fff; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3); }
        .sev-info { background: linear-gradient(135deg, #4B5563, #6B7280); color: #E5E7EB; }

        /* ═══════════════════════════════════════════════
           Health Score Card
           ═══════════════════════════════════════════════ */
        .health-card {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.7) 100%);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 20px;
            padding: 28px;
            text-align: center;
            margin-bottom: 16px;
            transition: all 0.35s ease;
            position: relative;
            overflow: hidden;
        }
        .health-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, #4ADE80, #22D3EE, #8B5CF6);
        }
        .health-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 40px rgba(59, 130, 246, 0.12);
        }
        .health-card .score {
            font-size: 3.5rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            background: linear-gradient(135deg, #4ADE80, #22D3EE);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .health-card .grade {
            font-size: 1.5rem;
            color: #94A3B8;
            font-weight: 600;
        }
        .health-card .label {
            color: #64748B;
            font-size: 0.8rem;
            margin-top: 6px;
            font-weight: 500;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* ═══════════════════════════════════════════════
           Finding Card
           ═══════════════════════════════════════════════ */
        .finding-card {
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.9) 0%, rgba(17, 24, 39, 0.7) 100%);
            backdrop-filter: blur(8px);
            border-left: 4px solid #3B82F6;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 12px;
            transition: all 0.3s ease;
        }
        .finding-card:hover {
            transform: translateX(4px);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }
        .finding-card.sev-border-critical { border-left-color: #DC2626; }
        .finding-card.sev-border-high { border-left-color: #EA580C; }
        .finding-card.sev-border-medium { border-left-color: #D97706; }
        .finding-card.sev-border-low { border-left-color: #2563EB; }
        .finding-card.sev-border-info { border-left-color: #4B5563; }

        /* ═══════════════════════════════════════════════
           Buttons — Premium styling
           ═══════════════════════════════════════════════ */
        .stButton > button {
            border-radius: 10px !important;
            font-weight: 600 !important;
            letter-spacing: 0.01em !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
            border: 1px solid rgba(139, 92, 246, 0.2) !important;
        }
        .stButton > button:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 20px rgba(139, 92, 246, 0.25) !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%) !important;
            border: none !important;
            color: white !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #9D74F7 0%, #8B5CF6 100%) !important;
            box-shadow: 0 6px 24px rgba(139, 92, 246, 0.35) !important;
        }

        /* ═══════════════════════════════════════════════
           Download buttons
           ═══════════════════════════════════════════════ */
        .stDownloadButton > button {
            border-radius: 10px !important;
            font-weight: 500 !important;
            border: 1px solid rgba(6, 182, 212, 0.25) !important;
            transition: all 0.3s ease !important;
        }
        .stDownloadButton > button:hover {
            border-color: rgba(6, 182, 212, 0.5) !important;
            box-shadow: 0 4px 16px rgba(6, 182, 212, 0.15) !important;
            transform: translateY(-1px) !important;
        }

        /* ═══════════════════════════════════════════════
           Expander Styling
           ═══════════════════════════════════════════════ */
        .streamlit-expanderHeader {
            background: rgba(26, 26, 50, 0.5) !important;
            border-radius: 10px !important;
            border: 1px solid rgba(139, 92, 246, 0.1) !important;
            font-weight: 500 !important;
        }
        .streamlit-expanderContent {
            border: 1px solid rgba(139, 92, 246, 0.08) !important;
            border-top: none !important;
            border-radius: 0 0 10px 10px !important;
        }

        /* ═══════════════════════════════════════════════
           Input Fields
           ═══════════════════════════════════════════════ */
        .stTextInput > div > div > input {
            border-radius: 10px !important;
            border: 1px solid rgba(139, 92, 246, 0.2) !important;
            background: rgba(15, 15, 30, 0.8) !important;
            transition: all 0.3s ease !important;
        }
        .stTextInput > div > div > input:focus {
            border-color: rgba(139, 92, 246, 0.5) !important;
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1) !important;
        }

        /* ═══════════════════════════════════════════════
           Select boxes
           ═══════════════════════════════════════════════ */
        .stSelectbox > div > div {
            border-radius: 10px !important;
        }

        /* ═══════════════════════════════════════════════
           Chat messages
           ═══════════════════════════════════════════════ */
        .stChatMessage {
            border-radius: 14px !important;
            border: 1px solid rgba(139, 92, 246, 0.08) !important;
            background: rgba(20, 20, 40, 0.5) !important;
            backdrop-filter: blur(8px) !important;
        }

        /* ═══════════════════════════════════════════════
           Chat input — styled (ChatGPT-style layout)
           ═══════════════════════════════════════════════ */
        [data-testid="stChatInput"] {
            max-width: 100% !important;
        }

        [data-testid="stChatInput"] textarea {
            border-radius: 14px !important;
            border: 1px solid rgba(139, 92, 246, 0.25) !important;
            background: rgba(20, 20, 45, 0.9) !important;
            padding: 14px 18px !important;
            font-size: 0.95rem !important;
            transition: all 0.3s ease !important;
            color: #E2E8F0 !important;
        }

        [data-testid="stChatInput"] textarea:focus {
            border-color: rgba(139, 92, 246, 0.5) !important;
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1), 0 4px 20px rgba(139, 92, 246, 0.15) !important;
        }

        [data-testid="stChatInput"] button {
            border-radius: 10px !important;
            background: linear-gradient(135deg, #8B5CF6, #7C3AED) !important;
            transition: all 0.3s ease !important;
        }

        [data-testid="stChatInput"] button:hover {
            background: linear-gradient(135deg, #9D74F7, #8B5CF6) !important;
            box-shadow: 0 4px 16px rgba(139, 92, 246, 0.3) !important;
            transform: scale(1.05) !important;
        }

        /* ═══════════════════════════════════════════════
           Metrics — clean look
           ═══════════════════════════════════════════════ */
        [data-testid="stMetric"] {
            background: rgba(26, 26, 50, 0.5);
            border: 1px solid rgba(139, 92, 246, 0.1);
            border-radius: 12px;
            padding: 14px 18px;
        }
        [data-testid="stMetricValue"] {
            font-weight: 700 !important;
        }

        /* ═══════════════════════════════════════════════
           Progress bar
           ═══════════════════════════════════════════════ */
        .stProgress > div > div > div {
            background: linear-gradient(90deg, #8B5CF6, #06B6D4) !important;
            border-radius: 10px !important;
        }

        /* ═══════════════════════════════════════════════
           Welcome hero section
           ═══════════════════════════════════════════════ */
        .hero-container {
            background: linear-gradient(135deg, rgba(15, 15, 35, 0.95) 0%, rgba(26, 26, 60, 0.8) 100%);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(139, 92, 246, 0.15);
            border-radius: 24px;
            padding: 48px 40px;
            text-align: center;
            margin: 20px 0 30px 0;
            position: relative;
            overflow: hidden;
        }
        .hero-container::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, #8B5CF6, #06B6D4, #8B5CF6);
            background-size: 200% 100%;
            animation: gradient-shift 3s ease infinite;
        }
        .hero-container::after {
            content: '';
            position: absolute;
            top: -50%; left: -50%;
            width: 200%; height: 200%;
            background: radial-gradient(circle at 50% 50%, rgba(139, 92, 246, 0.06) 0%, transparent 50%);
            pointer-events: none;
        }
        .hero-title {
            font-size: 2.8rem;
            font-weight: 900;
            letter-spacing: -0.04em;
            line-height: 1.1;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #ffffff 0%, #C4B5FD 40%, #06B6D4 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .hero-subtitle {
            font-size: 1.1rem;
            color: #94A3B8;
            font-weight: 400;
            line-height: 1.6;
            max-width: 600px;
            margin: 0 auto;
        }

        /* ═══════════════════════════════════════════════
           Feature cards — welcome page
           ═══════════════════════════════════════════════ */
        .feature-card {
            background: linear-gradient(135deg, rgba(20, 20, 45, 0.8) 0%, rgba(30, 30, 60, 0.5) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(139, 92, 246, 0.12);
            border-radius: 16px;
            padding: 24px 20px;
            text-align: center;
            transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
            height: 100%;
        }
        .feature-card:hover {
            border-color: rgba(139, 92, 246, 0.3);
            transform: translateY(-4px);
            box-shadow: 0 12px 40px rgba(139, 92, 246, 0.1);
        }
        .feature-icon {
            font-size: 2.2rem;
            margin-bottom: 12px;
            display: block;
        }
        .feature-title {
            font-size: 1rem;
            font-weight: 700;
            color: #E2E8F0;
            margin-bottom: 8px;
        }
        .feature-desc {
            font-size: 0.82rem;
            color: #64748B;
            line-height: 1.5;
        }

        /* ═══════════════════════════════════════════════
           Section headers
           ═══════════════════════════════════════════════ */
        .section-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 6px;
        }
        .section-header .icon {
            font-size: 1.5rem;
        }
        .section-header .title {
            font-size: 1.4rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #E2E8F0, #A78BFA);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        /* ═══════════════════════════════════════════════
           History project card
           ═══════════════════════════════════════════════ */
        .project-card {
            background: linear-gradient(135deg, rgba(20, 20, 45, 0.7) 0%, rgba(26, 26, 50, 0.5) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(139, 92, 246, 0.1);
            border-radius: 14px;
            padding: 18px 22px;
            margin-bottom: 10px;
            transition: all 0.3s ease;
        }
        .project-card:hover {
            border-color: rgba(139, 92, 246, 0.25);
            box-shadow: 0 4px 20px rgba(139, 92, 246, 0.08);
        }

        /* ═══════════════════════════════════════════════
           Code blocks
           ═══════════════════════════════════════════════ */
        .stCodeBlock {
            border-radius: 12px !important;
            border: 1px solid rgba(139, 92, 246, 0.1) !important;
        }

        /* ═══════════════════════════════════════════════
           Radio buttons — pill style  
           ═══════════════════════════════════════════════ */
        .stRadio > div {
            gap: 8px !important;
        }
        .stRadio [role="radiogroup"] label {
            border-radius: 10px !important;
            padding: 6px 16px !important;
            border: 1px solid rgba(139, 92, 246, 0.15) !important;
            transition: all 0.3s ease !important;
        }

        /* ═══════════════════════════════════════════════
           Popover styling
           ═══════════════════════════════════════════════ */
        [data-testid="stPopover"] > div {
            border-radius: 14px !important;
            border: 1px solid rgba(139, 92, 246, 0.2) !important;
        }

        /* ═══════════════════════════════════════════════
           Multiselect tags
           ═══════════════════════════════════════════════ */
        [data-baseweb="tag"] {
            border-radius: 8px !important;
            background: rgba(139, 92, 246, 0.15) !important;
            border: 1px solid rgba(139, 92, 246, 0.25) !important;
        }

        /* ═══════════════════════════════════════════════
           Divider
           ═══════════════════════════════════════════════ */
        hr {
            border-color: rgba(139, 92, 246, 0.1) !important;
        }

        /* ═══════════════════════════════════════════════
           Tooltips
           ═══════════════════════════════════════════════ */
        .stTooltipIcon {
            color: #8B5CF6 !important;
        }

        /* ═══════════════════════════════════════════════
           Sidebar metric cards
           ═══════════════════════════════════════════════ */
        .sidebar-stat {
            background: linear-gradient(135deg, rgba(26, 26, 50, 0.7) 0%, rgba(20, 20, 40, 0.5) 100%);
            border: 1px solid rgba(139, 92, 246, 0.12);
            border-radius: 12px;
            padding: 12px 16px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .sidebar-stat .label {
            font-size: 0.8rem;
            color: #64748B;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .sidebar-stat .value {
            font-size: 1.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #8B5CF6, #06B6D4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        /* ═══════════════════════════════════════════════
           Powered by badge
           ═══════════════════════════════════════════════ */
        .powered-by {
            font-size: 0.72rem;
            color: #475569;
            padding: 6px 12px;
            background: rgba(15, 15, 30, 0.5);
            border-radius: 8px;
            border: 1px solid rgba(71, 85, 105, 0.15);
            text-align: center;
            margin-top: 4px;
        }
        .powered-by strong {
            color: #8B5CF6;
        }
    </style>
    """, unsafe_allow_html=True)
