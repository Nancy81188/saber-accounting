# ai_mapper.py
import openai # Or your preferred LLM client

# We only send a sample of the chart to the AI to save tokens, 
# or we use the full list if it fits in the context window.
from lebanese_accounts import LEBANESE_ACCOUNTS

def suggest_account(expense_description):
    """
    Takes an expense description and suggests the most 
    appropriate Lebanese Chart of Account code.
    """
    
    # 1. Prepare the context: We give the AI a few examples of your chart
    # To be efficient, we can filter the chart for "Expense" types (usually codes starting with 6)
    expense_accounts = [acc for acc in LEBANESE_ACCOUNTS if acc[0].startswith('6')]
    
    # Format the list for the AI
    chart_context = "\n".join([f"Code: {a[0]} | Name: {a[1]} | Arabic: {a[2]}" for a in expense_accounts])

    prompt = f"""
    You are an expert Lebanese Accountant. 
    Below is a list of expense accounts from the Lebanese Standard Chart of Accounts (PCGL).
    
    Chart:
    {chart_context}
    
    User Expense: "{expense_description}"
    
    Task: Find the most accurate Account Code for this expense.
    Return ONLY a JSON object in this format:
    {{
      "code": "CODE_HERE",
      "name": "ACCOUNT_NAME_HERE",
      "confidence": 0.0 to 1.0,
      "reason": "Brief explanation why"
    }}
    """

    try:
        # Replace with your actual AI API call (Gemma, GPT, etc.)
        response = openai.ChatCompletion.create(
            model="gpt-4o", # or gemma-2-9b
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return response.choices[0].message.content
    except Exception as e:
        return {"error": str(e)}
