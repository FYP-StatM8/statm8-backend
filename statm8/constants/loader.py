from langchain_core.prompts import ChatPromptTemplate


DATASET_SUMMARY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are an expert data analyst. Given information about a dataset including its demographics and sample rows, provide a comprehensive yet concise summary.

Your summary should include:
1. A brief overview of what the dataset appears to contain
2. Key characteristics and patterns you observe
3. Data quality observations (missing values, data types, etc.)
4. Potential use cases or analyses that could be performed
5. Any notable insights or anomalies you detect

Be specific and actionable in your analysis."""),
    ("user", """Dataset Demographics:
{demographics}

Sample Rows:
{sample_rows}

Please provide a comprehensive summary of this dataset.""")
])