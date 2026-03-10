import streamlit as st

def load_css():
    """Injects custom CSS for the application."""
    st.markdown("""
    <style>
        /* Dark-themed stat cards */
        .stat-card {
            background: linear-gradient(135deg, #1e1e2f 0%, #2d2d44 100%);
            border: 1px solid #3a3a5c;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            margin-bottom: 10px;
        }
        .stat-card h2 {
            font-size: 2rem;
            margin: 0;
            background: linear-gradient(90deg, #7c3aed, #06b6d4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stat-card p { color: #94a3b8; margin: 4px 0 0 0; font-size: 0.85rem; }
        /* Status badge */
        .badge-ok   { color:#4ade80; font-weight:600; }
        .badge-err  { color:#f87171; font-weight:600; }
        /* Section divider */
        .section-divider { border-top: 1px solid #334155; margin: 1.5rem 0; }
        /* Diagram result card */
        .diagram-card {
            background: #1a1a2e;
            border: 1px solid #3a3a5c;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .diagram-card h4 { color: #a78bfa; margin-bottom: 8px; }
        /* Security severity badges */
        .sev-badge { display: inline-block; padding: 2px 10px; border-radius: 6px;
                     font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; }
        .sev-critical { background: #dc2626; color: #fff; }
        .sev-high { background: #ea580c; color: #fff; }
        .sev-medium { background: #d97706; color: #fff; }
        .sev-low { background: #2563eb; color: #fff; }
        .sev-info { background: #4b5563; color: #e5e7eb; }
        /* Health score card */
        .health-card {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border: 2px solid #3b82f6;
            border-radius: 16px;
            padding: 24px;
            text-align: center;
            margin-bottom: 16px;
        }
        .health-card .score { font-size: 3.5rem; font-weight: 800;
            background: linear-gradient(90deg, #4ade80, #22d3ee);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .health-card .grade { font-size: 1.5rem; color: #94a3b8; }
        .health-card .label { color: #64748b; font-size: 0.85rem; margin-top: 4px; }
        /* Finding card */
        .finding-card {
            background: #111827;
            border-left: 4px solid #3b82f6;
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 10px;
        }
        .finding-card.sev-border-critical { border-left-color: #dc2626; }
        .finding-card.sev-border-high { border-left-color: #ea580c; }
        .finding-card.sev-border-medium { border-left-color: #d97706; }
        .finding-card.sev-border-low { border-left-color: #2563eb; }
        .finding-card.sev-border-info { border-left-color: #4b5563; }
    </style>
    """, unsafe_allow_html=True)
