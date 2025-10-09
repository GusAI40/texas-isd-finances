"""
Import cleaned financial data to Supabase
"""
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

def import_data():
    """Import CSV data to Supabase"""
    print("=" * 60)
    print("Texas ISD Financial Data Import")
    print("=" * 60)
    
    # Get database URL
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL not found in .env file")
    
    print(f"\n✓ Database URL loaded")
    
    # Create engine
    print("✓ Creating database connection...")
    engine = create_engine(db_url)
    
    # Load CSV
    csv_path = Path("data/texas_finance_clean.csv")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    print(f"✓ Loading data from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    print(f"✓ Loaded {len(df):,} records with {len(df.columns)} columns")
    
    # Import to database
    print("\n⏳ Importing data to Supabase...")
    print("   This may take 2-3 minutes...")
    
    df.to_sql(
        "texas_school_finance",
        engine,
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi"
    )
    
    print("\n" + "=" * 60)
    print("✅ SUCCESS! Data imported successfully!")
    print("=" * 60)
    print(f"\n📊 Import Summary:")
    print(f"   • Total records: {len(df):,}")
    print(f"   • Total columns: {len(df.columns)}")
    print(f"   • Year range: {df['year'].min()} - {df['year'].max()}")
    print(f"   • Districts: {df['district_number'].nunique():,}")
    print("\n✓ Database is ready for queries!")
    print("\nNext steps:")
    print("  1. Test NLP engine: python src/nlp_engine.py")
    print("  2. Start API server: uvicorn src.api:app --reload")
    print()

if __name__ == "__main__":
    try:
        import_data()
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print("\nTroubleshooting:")
        print("  • Check that .env file exists with SUPABASE_DB_URL")
        print("  • Verify data/texas_finance_clean.csv exists")
        print("  • Ensure virtual environment is activated")
