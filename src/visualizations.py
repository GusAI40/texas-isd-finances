"""
Sample visualization functions for Texas School Finance data
"""
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict, Any

def plot_district_trend(data: List[Dict[str, Any]], district_name: str, metric: str = "spend_per_student"):
    """
    Create a line plot showing trend over time for a district
    
    Args:
        data: List of dictionaries with year and metric data
        district_name: Name of the district
        metric: Which metric to plot (spend_per_student, total_revenue, etc.)
    """
    df = pd.DataFrame(data)
    
    plt.figure(figsize=(10, 6))
    plt.plot(df['year'], df[metric], marker='o', linewidth=2, markersize=8)
    plt.title(f"{district_name} - {metric.replace('_', ' ').title()} Trend", fontsize=16)
    plt.xlabel("Year", fontsize=12)
    plt.ylabel(metric.replace('_', ' ').title(), fontsize=12)
    plt.grid(True, alpha=0.3)
    
    # Format y-axis for currency
    if 'spend' in metric or 'revenue' in metric:
        ax = plt.gca()
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    plt.tight_layout()
    return plt

def plot_district_comparison(data: List[Dict[str, Any]], metric: str = "spend_per_student"):
    """
    Create a bar chart comparing multiple districts
    
    Args:
        data: List of dictionaries with district_name and metric data
        metric: Which metric to compare
    """
    df = pd.DataFrame(data)
    
    # Sort by metric value
    df = df.sort_values(metric, ascending=True)
    
    plt.figure(figsize=(10, 8))
    plt.barh(df['district_name'], df[metric])
    plt.xlabel(metric.replace('_', ' ').title(), fontsize=12)
    plt.title(f"District Comparison - {metric.replace('_', ' ').title()}", fontsize=16)
    
    # Format x-axis for currency
    if 'spend' in metric or 'revenue' in metric:
        ax = plt.gca()
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    plt.tight_layout()
    return plt

def create_interactive_trend(data: List[Dict[str, Any]], districts: List[str], metric: str = "spend_per_student"):
    """
    Create an interactive Plotly line chart for multiple districts
    
    Args:
        data: List of dictionaries with district, year, and metric data
        districts: List of district names to include
        metric: Which metric to plot
    """
    df = pd.DataFrame(data)
    df = df[df['district_name'].isin(districts)]
    
    fig = px.line(df, x='year', y=metric, color='district_name',
                  title=f"{metric.replace('_', ' ').title()} by District Over Time",
                  labels={
                      'year': 'Year',
                      metric: metric.replace('_', ' ').title(),
                      'district_name': 'District'
                  })
    
    # Update layout
    fig.update_layout(
        hovermode='x unified',
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        )
    )
    
    # Format y-axis for currency
    if 'spend' in metric or 'revenue' in metric:
        fig.update_yaxis(tickformat='$,.0f')
    
    return fig

def create_anomaly_heatmap(anomaly_data: List[Dict[str, Any]]):
    """
    Create a heatmap showing anomaly flags by district and year
    
    Args:
        anomaly_data: List of dictionaries with anomaly flag data
    """
    df = pd.DataFrame(anomaly_data)
    
    # Create a binary matrix of anomalies
    anomaly_cols = ['revenue_drop_flag', 'spend_spike_flag', 'per_student_spike_flag', 'enrollment_decline_flag']
    
    # Pivot data to create matrix
    pivot_data = []
    for _, row in df.iterrows():
        for col in anomaly_cols:
            if row.get(col, False):
                pivot_data.append({
                    'district': row['district_name'],
                    'year': row['year'],
                    'anomaly_type': col.replace('_flag', '').replace('_', ' ').title(),
                    'value': 1
                })
    
    if not pivot_data:
        return None
    
    pivot_df = pd.DataFrame(pivot_data)
    matrix = pivot_df.pivot_table(index='district', columns=['year', 'anomaly_type'], 
                                   values='value', fill_value=0)
    
    # Create heatmap
    plt.figure(figsize=(15, 10))
    sns.heatmap(matrix, cmap='YlOrRd', cbar_kws={'label': 'Anomaly Present'})
    plt.title('Financial Anomalies by District and Year', fontsize=16)
    plt.xlabel('Year / Anomaly Type', fontsize=12)
    plt.ylabel('District', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    return plt

def create_enrollment_vs_spending_scatter(data: List[Dict[str, Any]], year: int):
    """
    Create a scatter plot of enrollment vs spending per student
    
    Args:
        data: List of dictionaries with enrollment and spending data
        year: Year to analyze
    """
    df = pd.DataFrame(data)
    df = df[df['year'] == year]
    
    # Remove outliers and null values
    df = df.dropna(subset=['enrollment', 'spend_per_student'])
    df = df[(df['enrollment'] > 0) & (df['spend_per_student'] > 0)]
    
    fig = px.scatter(df, 
                     x='enrollment', 
                     y='spend_per_student',
                     hover_data=['district_name'],
                     title=f'Enrollment vs Spending per Student ({year})',
                     labels={
                         'enrollment': 'Student Enrollment',
                         'spend_per_student': 'Spending per Student ($)'
                     })
    
    # Add trendline
    fig.add_trace(
        go.Scatter(x=df['enrollment'], 
                   y=df['spend_per_student'].rolling(window=5).mean().sort_values(),
                   mode='lines',
                   name='Trend',
                   line=dict(color='red', dash='dash'))
    )
    
    fig.update_xaxis(type='log', title='Student Enrollment (log scale)')
    fig.update_yaxis(tickformat='$,.0f')
    
    return fig

# Example usage
if __name__ == "__main__":
    # Sample data for testing
    sample_trend_data = [
        {'year': 2018, 'spend_per_student': 10500, 'district_name': 'DALLAS ISD'},
        {'year': 2019, 'spend_per_student': 10800, 'district_name': 'DALLAS ISD'},
        {'year': 2020, 'spend_per_student': 11200, 'district_name': 'DALLAS ISD'},
        {'year': 2021, 'spend_per_student': 11500, 'district_name': 'DALLAS ISD'},
        {'year': 2022, 'spend_per_student': 11900, 'district_name': 'DALLAS ISD'},
    ]
    
    # Create and show sample plot
    plt_obj = plot_district_trend(sample_trend_data, "DALLAS ISD")
    plt_obj.show()
