import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

def main():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE company_year_graph_features ADD COLUMN IF NOT EXISTS related_party_state VARCHAR(50) DEFAULT 'no_note_disclosed'"))
        print("Successfully ensured related_party_state column in company_year_graph_features.")

if __name__ == "__main__":
    main()
