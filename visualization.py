"""
Visualization Utilities for Data Coworker
Automatic chart generation based on query results
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, List, Dict


class DataVisualizer:
    """
    Automatic visualization generator.
    Analyzes data and query to choose best chart type.
    """
    
    def __init__(self):
        self.color_scheme = {
            'primary': '#667eea',
            'secondary': '#764ba2',
            'success': '#48bb78',
            'warning': '#f6ad55',
            'danger': '#f56565',
            'info': '#4299e1'
        }
    
    def auto_visualize(self, df: pd.DataFrame, question: str = "") -> Optional[go.Figure]:
        """
        Automatically choose and create best visualization.
        
        Args:
            df: DataFrame with query results
            question: Original user question (helps determine intent)
            
        Returns:
            Plotly figure or None if no visualization needed
        """
        if df.empty:
            return None
        
        # Detect visualization type from question keywords
        question_lower = question.lower()
        
        # Time series detection
        if any(keyword in question_lower for keyword in ['trend', 'over time', 'daily', 'monthly', 'weekly']):
            return self.create_time_series(df)
        
        # Comparison detection
        if any(keyword in question_lower for keyword in ['compare', 'vs', 'versus', 'by industry', 'by plan']):
            return self.create_comparison_chart(df)
        
        # Distribution detection
        if any(keyword in question_lower for keyword in ['distribution', 'spread', 'histogram']):
            return self.create_distribution(df)
        
        # Composition detection
        if any(keyword in question_lower for keyword in ['breakdown', 'composition', 'percentage', 'share']):
            return self.create_composition_chart(df)
        
        # Correlation detection
        if any(keyword in question_lower for keyword in ['correlation', 'relationship', 'scatter']):
            return self.create_scatter(df)
        
        # Default: try to infer from data
        return self.infer_visualization(df)
    
    def infer_visualization(self, df: pd.DataFrame) -> Optional[go.Figure]:
        """
        Infer best visualization from data structure.
        
        Args:
            df: DataFrame to visualize
            
        Returns:
            Plotly figure
        """
        num_rows = len(df)
        num_cols = len(df.columns)
        
        # Too many rows for detailed viz
        if num_rows > 100:
            return self.create_summary_metrics(df)
        
        # Single metric
        if num_rows == 1 and num_cols == 1:
            return self.create_metric_card(df)
        
        # Single row of metrics
        if num_rows == 1:
            return self.create_metrics_dashboard(df)
        
        # Two columns: likely category vs value
        if num_cols == 2:
            # Check if first column is date-like
            if pd.api.types.is_datetime64_any_dtype(df.iloc[:, 0]):
                return self.create_time_series(df)
            else:
                return self.create_bar_chart(df)
        
        # Multiple numeric columns: multi-line chart
        if num_cols > 2:
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) >= 2:
                return self.create_multi_metric_chart(df)
        
        # Default: table is fine
        return None
    
    def create_time_series(self, df: pd.DataFrame) -> go.Figure:
        """Create time series line chart"""
        # Find date column
        date_col = None
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]) or 'date' in col.lower():
                date_col = col
                break
        
        if not date_col:
            date_col = df.columns[0]
        
        # Get numeric columns
        value_cols = df.select_dtypes(include=['number']).columns
        
        fig = go.Figure()
        
        for col in value_cols:
            fig.add_trace(go.Scatter(
                x=df[date_col],
                y=df[col],
                mode='lines+markers',
                name=col.replace('_', ' ').title(),
                line=dict(width=3),
                marker=dict(size=8)
            ))
        
        fig.update_layout(
            title="Time Series Analysis",
            xaxis_title=date_col.replace('_', ' ').title(),
            yaxis_title="Value",
            hovermode='x unified',
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_comparison_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create comparison bar chart"""
        # Assume first column is category, second is value
        category_col = df.columns[0]
        value_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        
        fig = px.bar(
            df,
            x=category_col,
            y=value_col,
            title=f"{value_col.replace('_', ' ').title()} by {category_col.replace('_', ' ').title()}",
            color=category_col,
            text=value_col
        )
        
        fig.update_traces(texttemplate='%{text:.2f}', textposition='outside')
        fig.update_layout(
            showlegend=False,
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_bar_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create simple bar chart"""
        x_col = df.columns[0]
        y_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        
        fig = go.Figure(data=[
            go.Bar(
                x=df[x_col],
                y=df[y_col],
                marker_color=self.color_scheme['primary'],
                text=df[y_col],
                texttemplate='%{text:.2f}',
                textposition='outside'
            )
        ])
        
        fig.update_layout(
            title=f"{y_col.replace('_', ' ').title()}",
            xaxis_title=x_col.replace('_', ' ').title(),
            yaxis_title=y_col.replace('_', ' ').title(),
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_composition_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create pie chart for composition"""
        label_col = df.columns[0]
        value_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        
        fig = px.pie(
            df,
            names=label_col,
            values=value_col,
            title=f"{value_col.replace('_', ' ').title()} Distribution",
            hole=0.3  # Donut chart
        )
        
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_distribution(self, df: pd.DataFrame) -> go.Figure:
        """Create histogram for distribution"""
        # Get first numeric column
        numeric_col = df.select_dtypes(include=['number']).columns[0]
        
        fig = px.histogram(
            df,
            x=numeric_col,
            nbins=20,
            title=f"Distribution of {numeric_col.replace('_', ' ').title()}"
        )
        
        fig.update_layout(
            xaxis_title=numeric_col.replace('_', ' ').title(),
            yaxis_title="Count",
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_scatter(self, df: pd.DataFrame) -> go.Figure:
        """Create scatter plot for correlation"""
        numeric_cols = df.select_dtypes(include=['number']).columns
        
        if len(numeric_cols) < 2:
            return None
        
        x_col = numeric_cols[0]
        y_col = numeric_cols[1]
        
        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            title=f"{y_col.replace('_', ' ').title()} vs {x_col.replace('_', ' ').title()}",
            trendline="ols"  # Add regression line
        )
        
        fig.update_layout(
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_multi_metric_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create chart with multiple metrics"""
        # First column is usually category/time
        x_col = df.columns[0]
        numeric_cols = df.select_dtypes(include=['number']).columns
        
        fig = go.Figure()
        
        for col in numeric_cols:
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[col],
                mode='lines+markers',
                name=col.replace('_', ' ').title()
            ))
        
        fig.update_layout(
            title="Multi-Metric Analysis",
            xaxis_title=x_col.replace('_', ' ').title(),
            yaxis_title="Value",
            hovermode='x unified',
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_metrics_dashboard(self, df: pd.DataFrame) -> go.Figure:
        """Create dashboard of metric cards"""
        # For single row with multiple columns
        metrics = []
        for col in df.columns:
            value = df[col].iloc[0]
            metrics.append({
                'name': col.replace('_', ' ').title(),
                'value': value
            })
        
        # Create indicator chart
        fig = go.Figure()
        
        for i, metric in enumerate(metrics):
            fig.add_trace(go.Indicator(
                mode="number",
                value=metric['value'],
                title={'text': metric['name']},
                domain={'row': 0, 'column': i}
            ))
        
        fig.update_layout(
            grid={'rows': 1, 'columns': len(metrics), 'pattern': "independent"},
            template='plotly_white',
            height=300
        )
        
        return fig
    
    def create_metric_card(self, df: pd.DataFrame) -> go.Figure:
        """Create single metric indicator"""
        col = df.columns[0]
        value = df[col].iloc[0]
        
        fig = go.Figure(go.Indicator(
            mode="number",
            value=value,
            title={'text': col.replace('_', ' ').title(), 'font': {'size': 24}},
            number={'font': {'size': 48}}
        ))
        
        fig.update_layout(
            template='plotly_white',
            height=300
        )
        
        return fig
    
    def create_summary_metrics(self, df: pd.DataFrame) -> go.Figure:
        """Create summary statistics for large datasets"""
        numeric_cols = df.select_dtypes(include=['number']).columns
        
        if len(numeric_cols) == 0:
            return None
        
        # Calculate summary stats
        summary = df[numeric_cols].describe().T
        
        fig = go.Figure(data=[
            go.Table(
                header=dict(
                    values=['Metric'] + list(summary.columns),
                    fill_color=self.color_scheme['primary'],
                    font=dict(color='white', size=14),
                    align='left'
                ),
                cells=dict(
                    values=[summary.index] + [summary[col] for col in summary.columns],
                    fill_color='lavender',
                    align='left',
                    format=[None] + ['.2f'] * len(summary.columns)
                )
            )
        ])
        
        fig.update_layout(
            title="Summary Statistics",
            height=400
        )
        
        return fig
    
    def create_funnel(self, df: pd.DataFrame, stage_col: str, value_col: str) -> go.Figure:
        """Create funnel chart for conversion analysis"""
        fig = go.Figure(go.Funnel(
            y=df[stage_col],
            x=df[value_col],
            textposition="inside",
            textinfo="value+percent initial",
            marker=dict(color=self.color_scheme['primary'])
        ))
        
        fig.update_layout(
            title="Conversion Funnel",
            template='plotly_white',
            height=500
        )
        
        return fig
    
    def create_heatmap(self, df: pd.DataFrame) -> go.Figure:
        """Create correlation heatmap"""
        # Calculate correlation matrix
        numeric_df = df.select_dtypes(include=['number'])
        corr = numeric_df.corr()
        
        fig = go.Figure(data=go.Heatmap(
            z=corr.values,
            x=corr.columns,
            y=corr.columns,
            colorscale='RdBu',
            zmid=0
        ))
        
        fig.update_layout(
            title="Correlation Heatmap",
            template='plotly_white',
            height=500
        )
        
        return fig


# Global instance
_visualizer_instance = None

def get_visualizer() -> DataVisualizer:
    """Get global visualizer instance"""
    global _visualizer_instance
    if _visualizer_instance is None:
        _visualizer_instance = DataVisualizer()
    return _visualizer_instance
