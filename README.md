# Texas ISD Financial Data Portal

A comprehensive system for analyzing Texas Independent School District financial data from 2008-2024, featuring natural language querying, anomaly detection, and public transparency tools.

## 🎯 Project Goals

- **Scalable Oversight**: AI-powered anomaly detection across 1000+ districts
- **Public Accountability**: Citizen-friendly portal for viewing district finances  
- **Policy Feedback**: Data-driven insights for legislators and policymakers

## 🚀 Quick Start

See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions.

### Prerequisites
- Python 3.8+
- Supabase account
- OpenAI API key
- Excel data file (2008-2024 financial data)

### Basic Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp env_template.txt .env
# Edit .env with your credentials

# 3. Prepare data
python scripts/prepare_data.py

# 4. Start API
uvicorn src.api:app --reload
```

## 📁 Project Structure

```
texas-isd-finances/
├── data/                   # Processed data files
├── scripts/               # Data preparation scripts
│   └── prepare_data.py   # Excel to CSV converter
├── sql/                   # Database schemas
│   └── create_tables.sql # Supabase table definitions
├── src/                   # Source code
│   ├── api.py            # FastAPI service
│   ├── nlp_engine.py     # Natural language to SQL
│   └── visualizations.py # Chart generation
├── implementation_plan.md # Detailed implementation steps
└── requirements.txt      # Python dependencies
```

## 🔧 Key Features

### Natural Language Queries
Ask questions in plain English:
- "Show Dallas ISD spending per student 2020-2024"
- "Which districts have declining enrollment?"
- "Find anomalies in Houston area districts"

### Anomaly Detection
Automatic flagging of:
- Revenue drops >15% year-over-year
- Spending spikes >20% with flat enrollment
- Per-student spending increases >15%
- Enrollment declines >10%

### API Endpoints
- `POST /query` - Natural language queries
- `GET /districts` - List all districts
- `GET /district/{id}/summary` - District financials
- `GET /anomalies` - Flagged anomalies

## 📊 Data Schema

Main table: `texas_school_finance`
- 140+ financial metrics per district/year
- Primary key: (district_number, year)
- Covers: Revenue, expenditures, enrollment, debt

Views:
- `v_finance_summary` - Simplified public view
- `v_anomaly_flags` - Detected anomalies

## 🔒 Security

- Row-level security on base tables
- Read-only views for public access
- Separate database roles for different access levels

## 📈 Sample Visualizations

The system includes visualization functions for:
- Spending trends over time
- District comparisons
- Enrollment vs spending analysis
- Anomaly heatmaps

## 🚀 Deployment

1. **Database**: Supabase (managed Postgres)
2. **API**: FastAPI on Railway/Render/Fly.io
3. **Frontend**: Next.js on Vercel (optional)

## 📝 License

This project is designed for public transparency and accountability.

## 🤝 Contributing

This system is intended to promote transparency in Texas education funding. Contributions that enhance public access and understanding are welcome.
