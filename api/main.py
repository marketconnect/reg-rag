import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from dotenv import load_dotenv
from services.agent_service import create_agent

# --- Pydantic Models for API validation ---

class QuestionDetail(BaseModel):
    text: str
    imageBase64: Optional[str] = None

class QuestionPayload(BaseModel):
    question: QuestionDetail
    answers: List[str]
    correctAnswers: List[str]

class ParagraphLocation(BaseModel):
    doc_id: int
    chapter_id: int
    paragraph_id: int

# --- FastAPI Application Setup ---

# Load environment variables from .env file at the project root
load_dotenv()

app = FastAPI(
    title="Legal RAG API",
    description="API to find justifying paragraphs for legal questions using a ReAct Agent.",
    version="1.0.0"
)

# Create the agent executor once on startup to avoid reloading models on every request
agent_executor = create_agent()

@app.post("/find_paragraph", response_model=ParagraphLocation)
async def find_justifying_paragraph(payload: QuestionPayload):
    """
    Accepts a question with its correct answer(s) and returns the location
    of the document paragraph that justifies the answer.
    """
    question_text = payload.question.text
    correct_answers_text = ", ".join(payload.correctAnswers)
    
    # Format the input for the agent
    full_input = (
        f"Question: {question_text}\n"
        f"Correct Answer: {correct_answers_text}"
    )
    
    print(f"--- Invoking Agent with Input ---\n{full_input}\n---------------------------------")

    try:
        # Asynchronously invoke the agent
        response = await agent_executor.ainvoke({"input": full_input})
        
        # This is a special case for our specific agent setup.
        # If the agent hits the iteration limit, it might not return 'output'.
        if not response or 'output' not in response:
            raise HTTPException(status_code=404, detail="Agent failed to produce a result within the iteration limit.")
        
        agent_output_str = response.get('output')
        
        if not agent_output_str:
            raise HTTPException(status_code=500, detail="Agent did not produce an output.")

        # The agent is prompted to return a JSON string. We need to parse it.
        try:
            # Clean up potential markdown code fences from the LLM output
            if agent_output_str.strip().startswith("```json"):
                agent_output_str = agent_output_str.strip()[7:-4].strip()
            
            # Check if the agent failed and returned an error JSON
            if '"error":' in agent_output_str:
                error_data = json.loads(agent_output_str)
                raise HTTPException(status_code=404, detail=error_data.get("error", "Justification not found"))

            # Proceed if it's a success JSON
            result_data = json.loads(agent_output_str) 
            
            # Validate the result with our Pydantic model before returning
            validated_result = ParagraphLocation(**result_data)
            return validated_result

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"Error parsing agent's JSON output: {e}")
            print(f"Raw agent output: {agent_output_str}")
            raise HTTPException(
                status_code=500, 
                detail=f"Agent produced a malformed output. Raw output: {agent_output_str}"
            )

    except HTTPException as he:
        # Re-raise the HTTPException we created intentionally (like 404 Not Found)
        # so that FastAPI can handle it correctly.
        raise he

    except Exception as e:
        print(f"An unexpected error occurred during agent invocation: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Legal RAG API. Use the /docs endpoint to see the API documentation."} 