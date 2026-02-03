from langchain_core.prompts import ChatPromptTemplate


# VLM model configuration - using Groq's vision model
VLM_MODEL = "llama-3.2-90b-vision-preview"

# Prompt template for analyzing individual plots
PLOT_ANALYSIS_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are an expert data analyst skilled at interpreting data visualizations. 
Analyze the provided plot image and extract meaningful insights.

Your analysis should include:
1. **Plot Type**: Identify the type of visualization (histogram, scatter plot, heatmap, etc.)
2. **Key Observations**: What patterns, trends, or anomalies are visible?
3. **Statistical Insights**: Any notable statistical properties (distribution shape, correlations, outliers)
4. **Actionable Insights**: What decisions or further analyses does this suggest?

Be concise but thorough. Focus on insights that would be valuable for data-driven decision making."""),
    
    ("user", [
        {"type": "text", "text": "Analyze this data visualization from an EDA of the '{dataset_name}' dataset. Plot filename: {plot_filename}"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_base64}"}}
    ])
])

# Prompt template for summarizing all plot analyses
SUMMARY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are an expert data analyst. Given individual analyses of multiple plots from an EDA session,
synthesize them into a cohesive summary report.

Your summary should:
1. **Overall Dataset Character**: What type of data is this? What domain does it appear to be from?
2. **Key Findings**: The most important insights across all visualizations
3. **Data Quality Notes**: Any issues or concerns about the data
4. **Recommendations**: Suggested next steps for analysis or modeling
5. **Feature Importance**: Which features appear most significant?

Be professional and actionable in your recommendations."""),
    
    ("user", """Dataset: {dataset_name}

Individual Plot Analyses:
{plot_analyses}

Provide a comprehensive summary of the EDA findings.""")
])
