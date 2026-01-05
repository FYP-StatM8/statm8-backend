from langchain_core.prompts import ChatPromptTemplate


EDA_CODE_GENERATION_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are an expert data scientist specialized in Exploratory Data Analysis (EDA). 

CRITICAL: Return ONLY pure Python code. DO NOT use markdown code fences (no ```python or ```).

Given dataset information, generate Python code blocks for comprehensive EDA analysis. Each code block should:
1. Be self-contained and executable
2. Use pandas, matplotlib, seaborn, and numpy
3. Include proper error handling
4. Save plots to the specified output directory
5. Print meaningful insights

Generate code for the following analyses:
- Data overview and structure
- Missing value analysis
- Numerical feature distributions
- Categorical feature distributions
- Correlation analysis
- Outlier detection
- Feature relationships

Important: 
- Use 'df' as the DataFrame variable name
- Save plots using: plt.savefig(os.path.join(output_dir, 'plot_name.png'), bbox_inches='tight', dpi=300)
- Always close plots after saving: plt.close()
- Each code block should be independent and complete
- NO MARKDOWN FORMATTING - pure Python code only"""),
    
    ("user", """Dataset Information:
File Path: {file_path}
Total Rows: {total_rows}
Total Columns: {total_columns}

Column Details:
{columns_info}

Sample Data:
{sample_rows}

Output Directory: {output_dir}

{comments_section}

Generate Python code blocks for comprehensive EDA. Return ONLY valid Python code blocks separated by '### BLOCK_SEPARATOR ###'.
Each block should start with a comment describing what it does.""")
])


CODE_BLOCK_TEMPLATE = """
# {description}
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os

# Set style
sns.set_style('whitegrid')
plt.rcParams['figure.figsize'] = (12, 6)

# Load data
df = pd.read_csv('{file_path}')
output_dir = '{output_dir}'

{code}
"""